"""Reproducible PubMed discovery with exact membership and offline replay files."""

import hashlib
import calendar
import json
import math
import re
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.review.identity import normalize_pmid
from src.review.importers import load_records_bytes
from src.review.models import SearchRunSpec


BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
_ENDPOINTS = {"esearch.fcgi", "efetch.fcgi"}
_RECORD_TAGS = {"PubmedArticle", "PubmedBookArticle", "MedlineCitation"}
_CONTAINER_TAGS = {"PubmedArticleSet", "PubmedBookArticleSet", "MedlineCitationSet"}


class PubMedError(ValueError):
    """Credential-free PubMed configuration, transport, or capture failure."""


def _utc_now():
    return datetime.now(timezone.utc)


def _default_transport(url, data, timeout):
    request = Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    with urlopen(request, timeout=timeout) as response:
        return response.read()


class PubMedClient:
    """Serialized E-utilities POST requests with per-client rate limiting."""

    def __init__(self, email, api_key=None, tool="lit-rev-engine", *, transport=None, sleep=None, monotonic=None, timeout=30, max_attempts=3):
        if not isinstance(email, str) or not email.strip():
            raise PubMedError("PubMed requires a nonempty contact email")
        if not isinstance(tool, str) or not tool.strip():
            raise PubMedError("PubMed requires a nonempty tool name")
        if api_key is not None and (not isinstance(api_key, str) or not api_key.strip()):
            raise PubMedError("PubMed API key must be a nonempty string when supplied")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise PubMedError("PubMed timeout must be positive and finite")
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts < 1:
            raise PubMedError("PubMed maximum attempts must be a positive integer")
        self._email, self._api_key, self._tool = email, api_key, tool
        self._transport = _default_transport if transport is None else transport
        self._sleep = time.sleep if sleep is None else sleep
        self._monotonic = time.monotonic if monotonic is None else monotonic
        self._timeout, self._max_attempts = timeout, max_attempts
        self._interval = 0.1 if api_key else 1 / 3
        self._last_attempt = None
        self._lock = threading.Lock()

    def _throttle(self):
        now = self._monotonic()
        if self._last_attempt is not None:
            delay = self._interval - (now - self._last_attempt)
            if delay > 0:
                self._sleep(delay)
        self._last_attempt = self._monotonic()

    @staticmethod
    def _retry_delay(error, attempt):
        value = error.headers.get("Retry-After") if isinstance(error, HTTPError) and error.headers is not None else None
        if value:
            try:
                seconds = float(value)
                if math.isfinite(seconds) and seconds >= 0:
                    return seconds
            except (TypeError, ValueError):
                pass
            try:
                after = parsedate_to_datetime(value)
                if after.tzinfo is None:
                    after = after.replace(tzinfo=timezone.utc)
                return max(0.0, (after - _utc_now()).total_seconds())
            except (TypeError, ValueError, OverflowError):
                pass
        return min(60.0, 2.0 ** min(attempt, 6))

    def request(self, endpoint, params):
        if not isinstance(endpoint, str) or endpoint not in _ENDPOINTS:
            raise PubMedError("Unsupported PubMed endpoint")
        if not isinstance(params, dict) or any(not isinstance(key, str) for key in params):
            raise PubMedError("PubMed request parameters must be an object with string keys")
        if {"api_key", "email", "tool"}.intersection(params):
            raise PubMedError("Credentials and tool configuration belong to PubMedClient")
        operational = {**params, "tool": self._tool, "email": self._email}
        if self._api_key:
            operational["api_key"] = self._api_key
        try:
            data = urlencode(operational).encode("utf-8")
        except Exception:
            raise PubMedError("Unable to encode PubMed request parameters") from None
        with self._lock:
            for attempt in range(self._max_attempts):
                self._throttle()
                try:
                    response = self._transport(BASE_URL + endpoint, data, self._timeout)
                except HTTPError as error:
                    retry = error.code == 429 or 500 <= error.code <= 599
                    if not retry or attempt + 1 == self._max_attempts:
                        raise PubMedError(f"PubMed HTTP request failed (status {error.code})") from None
                    self._sleep(self._retry_delay(error, attempt))
                    continue
                except (URLError, TimeoutError, OSError) as error:
                    if attempt + 1 == self._max_attempts:
                        raise PubMedError("PubMed transport failed after bounded attempts") from None
                    self._sleep(self._retry_delay(error, attempt))
                    continue
                except Exception:
                    raise PubMedError("PubMed transport failed") from None
                if not isinstance(response, bytes):
                    raise PubMedError("PubMed transport must return response bytes")
                return response
        raise PubMedError("PubMed request did not complete")


def _tag(element):
    return element.tag.rsplit("}", 1)[-1]


def _parse_xml(payload, context):
    if not isinstance(payload, bytes):
        raise PubMedError(f"{context}: response must be bytes")
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeError:
        raise PubMedError(f"{context}: response must be UTF-8 XML") from None
    if re.search(r"<!ENTITY\b", text, re.I):
        raise PubMedError(f"{context}: XML ENTITY declarations are unsupported")
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        raise PubMedError(f"{context}: malformed XML response") from None
    if any(_tag(element).lower() in {"error", "errorlist"} for element in root.iter()):
        raise PubMedError(f"{context}: PubMed returned an XML error")
    return root


def _single(root, name, context):
    elements = [child for child in root if child.tag == name]
    if len(elements) != 1:
        raise PubMedError(f"{context}: expected one {name} element")
    return elements[0]


def _integer(root, name):
    element = _single(root, name, "ESearch")
    value = (element.text or "").strip()
    if list(element) or not re.fullmatch(r"[0-9]+", value):
        raise PubMedError(f"ESearch: {name} must be a nonnegative integer")
    try:
        return int(value)
    except ValueError:
        raise PubMedError(f"ESearch: invalid {name}") from None


def _search_membership(payload):
    root = _parse_xml(payload, "ESearch")
    if root.tag != "eSearchResult":
        raise PubMedError("ESearch: expected eSearchResult root")
    count = _integer(root, "Count")
    if count > 10000:
        raise PubMedError("PubMed query exceeds the 10,000-result ESearch limit; verified segmentation or EDirect export required")
    if _integer(root, "RetStart") != 0:
        raise PubMedError("ESearch: RetStart must be zero")
    maximum = _integer(root, "RetMax")
    identifiers = _single(root, "IdList", "ESearch")
    pmids, seen = [], set()
    for element in identifiers:
        if element.tag != "Id" or list(element):
            raise PubMedError("ESearch: IdList must contain PMID Id elements")
        try:
            pmid = normalize_pmid(element.text or "")
        except ValueError:
            raise PubMedError("ESearch: invalid PMID") from None
        if pmid is None or pmid in seen:
            raise PubMedError("ESearch: missing or duplicate PMID")
        pmids.append(pmid)
        seen.add(pmid)
    if count != len(pmids) or maximum != len(pmids):
        raise PubMedError("ESearch: Count/RetMax do not match complete captured PMID membership")
    translation = _single(root, "QueryTranslation", "ESearch")
    history = {}
    for element_name, field_name in (("WebEnv", "webenv"), ("QueryKey", "query_key")):
        elements = [child for child in root if child.tag == element_name]
        if len(elements) > 1:
            raise PubMedError(f"ESearch: repeated {element_name}")
        value = "".join(elements[0].itertext()) if elements else None
        if count and (value is None or not value.strip()):
            raise PubMedError("ESearch: nonzero results require history tokens")
        history[field_name] = value if value and value.strip() else None
    warnings = []
    for warning_list in (child for child in root if child.tag == "WarningList"):
        for warning in warning_list:
            warnings.append({"code": _tag(warning), "message": "".join(warning.itertext())})
    return count, pmids, "".join(translation.itertext()), history, warnings


def _filters(filters):
    if filters is None:
        return {}
    if not isinstance(filters, dict) or set(filters) - {"datetype", "mindate", "maxdate"}:
        raise PubMedError("PubMed filters must contain only datetype, mindate, maxdate")
    if filters and set(filters) != {"datetype", "mindate", "maxdate"}:
        raise PubMedError("PubMed date filters require datetype, mindate, and maxdate together")
    if any(not isinstance(value, str) or not value.strip() for value in filters.values()):
        raise PubMedError("PubMed date filter values must be nonempty strings")
    if filters and filters["datetype"] not in {"pdat", "edat"}:
        raise PubMedError("Unsupported PubMed date type")
    bounds = []
    for field in ("mindate", "maxdate"):
        if field not in filters:
            continue
        value = filters[field]
        try:
            if re.fullmatch(r"[0-9]{4}", value):
                bounds.append(date(int(value), 1 if field == "mindate" else 12, 1 if field == "mindate" else 31))
            elif re.fullmatch(r"[0-9]{4}/[0-9]{2}", value):
                year, month = map(int, value.split("/"))
                day = 1 if field == "mindate" else calendar.monthrange(year, month)[1]
                bounds.append(date(year, month, day))
            elif re.fullmatch(r"[0-9]{4}/[0-9]{2}/[0-9]{2}", value):
                bounds.append(date(*map(int, value.split("/"))))
            else:
                raise ValueError
        except ValueError:
            raise PubMedError("PubMed dates must be valid YYYY, YYYY/MM, or YYYY/MM/DD dates") from None
    if bounds and bounds[0] > bounds[1]:
        raise PubMedError("PubMed mindate must not be after maxdate")
    return dict(filters)


def _request(client, endpoint, params):
    try:
        response = client.request(endpoint, dict(params))
    except Exception:
        raise PubMedError(f"PubMed request failed for {endpoint}") from None
    if not isinstance(response, bytes):
        raise PubMedError(f"PubMed {endpoint} response must be bytes")
    return response


def _response_entry(endpoint, params, name, payload):
    return {"endpoint": endpoint, "params": dict(params), "response_file": name, "response_sha256": hashlib.sha256(payload).hexdigest()}


def _validated_batch(payload, expected):
    root = _parse_xml(payload, "EFetch")
    if _tag(root) in _RECORD_TAGS:
        elements = [root]
    elif _tag(root) in _CONTAINER_TAGS:
        elements = list(root)
    else:
        raise PubMedError("EFetch: unsupported PubMed XML root")
    if _tag(root) in _CONTAINER_TAGS and ((root.text or "").strip() or any((element.tail or "").strip() for element in elements)):
        raise PubMedError("EFetch: unexpected text outside citation records")
    try:
        records = load_records_bytes(payload, "pubmed_xml")
    except ValueError:
        raise PubMedError("EFetch: invalid bibliographic record or conflicting identifiers") from None
    found = {}
    for element, record in zip(elements, records):
        try:
            pmid = normalize_pmid(record.pmid)
        except ValueError:
            raise PubMedError("EFetch: invalid PMID") from None
        if pmid is None or pmid in found or pmid not in expected:
            raise PubMedError("EFetch: missing, duplicate, or unexpected PMID")
        found[pmid] = element
    if set(found) != set(expected):
        raise PubMedError("EFetch: missing PMID membership from requested batch")
    return found


def _batch_records(payload, path, expected):
    path.write_bytes(payload)
    return _validated_batch(payload, expected)


def capture_pubmed_search(query, destination, *, client=None, email=None, api_key=None, sort="pub_date", filters=None, batch_size=200):
    """Publish one complete ESearch membership and validated explicit-ID capture."""
    if not isinstance(query, str) or not query.strip():
        raise PubMedError("PubMed query must be nonempty")
    if not isinstance(sort, str) or sort not in {"pub_date", "relevance"}:
        raise PubMedError("PubMed sort must be pub_date or relevance")
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or not 1 <= batch_size <= 200:
        raise PubMedError("PubMed batch size must be an integer from 1 to 200")
    filters = _filters(filters)
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise PubMedError("PubMed capture destination must be absent")
    if client is None:
        client = PubMedClient(email, api_key)
    destination.parent.mkdir(parents=True, exist_ok=True)
    started_at = _utc_now().isoformat()
    with tempfile.TemporaryDirectory(prefix=f".{destination.name}.capture-", dir=destination.parent) as staged:
        staged = Path(staged)
        search_params = {"db": "pubmed", "term": query, "retmode": "xml", "retstart": 0, "retmax": 10000, "usehistory": "y", "sort": sort, **filters}
        searched_at = _utc_now().isoformat()
        payload = _request(client, "esearch.fcgi", search_params)
        count, pmids, translation, history, warnings = _search_membership(payload)
        (staged / "search.xml").write_bytes(payload)
        requests = [_response_entry("esearch.fcgi", search_params, "search.xml", payload)]
        found = {}
        for batch_number, start in enumerate(range(0, count, batch_size), 1):
            batch = pmids[start:start + batch_size]
            fetch_params = {"db": "pubmed", "id": ",".join(batch), "retmode": "xml"}
            payload = _request(client, "efetch.fcgi", fetch_params)
            (staged / "batches").mkdir(exist_ok=True)
            name = f"batches/{batch_number:04d}.xml"
            fetched = _batch_records(payload, staged / name, batch)
            if set(found).intersection(fetched):
                raise PubMedError("EFetch: duplicate PMID across batches")
            found.update(fetched)
            requests.append(_response_entry("efetch.fcgi", fetch_params, name, payload))
        if set(found) != set(pmids) or len(found) != count:
            raise PubMedError("EFetch: final PMID membership does not match captured search")
        combined = ET.Element("PubmedArticleSet")
        combined.extend(found[pmid] for pmid in pmids)
        combined_bytes = ET.tostring(combined, encoding="utf-8", xml_declaration=True)
        (staged / "records.xml").write_bytes(combined_bytes)
        try:
            replayed = load_records_bytes(combined_bytes, "pubmed_xml")
            replay_pmids = [normalize_pmid(record.pmid) for record in replayed]
        except ValueError:
            raise PubMedError("Combined PubMed XML failed importer replay") from None
        if replay_pmids != pmids:
            raise PubMedError("Combined PubMed XML order or membership differs from search")
        receipt = {
            "schema_version": 1, "source": "PubMed", "adapter": "lit-rev-engine.pubmed.v1",
            "query": query, "query_translation": translation, "sort": sort, "filters": filters,
            "started_at": started_at, "searched_at": searched_at, "completed_at": _utc_now().isoformat(),
            "reported_count": count, "pmids": pmids, "fetched_count": len(found), "complete": True,
            "warnings": warnings, "history": history, "requests": requests,
            "records_file": "records.xml", "records_sha256": hashlib.sha256(combined_bytes).hexdigest(),
        }
        (staged / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        # Exclusive reservation prevents replacement of an existing empty directory.
        try:
            destination.mkdir()
        except FileExistsError:
            raise PubMedError("PubMed capture destination must be absent") from None
        try:
            staged.rename(destination)
        except BaseException:
            destination.rmdir()
            raise
    return {"directory": str(destination), "xml_file": str(destination / "records.xml"), "receipt_file": str(destination / "receipt.json"), "receipt": receipt}


_RECEIPT_FIELDS = {
    "schema_version", "source", "adapter", "query", "query_translation", "sort", "filters",
    "started_at", "searched_at", "completed_at", "reported_count", "pmids", "fetched_count",
    "complete", "warnings", "history", "requests", "records_file", "records_sha256",
}
_REQUEST_FIELDS = {"endpoint", "params", "response_file", "response_sha256"}


def _strict_json(content):
    def pairs(entries):
        result = {}
        for key, value in entries:
            if key in result:
                raise ValueError("duplicate field")
            result[key] = value
        return result

    def constant(value):
        raise ValueError("nonfinite value")

    def number(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("nonfinite value")
        return parsed

    try:
        receipt = json.loads(content.decode("utf-8-sig"), object_pairs_hook=pairs, parse_constant=constant, parse_float=number)
    except (UnicodeError, ValueError, TypeError):
        raise PubMedError("PubMed receipt must be strict UTF-8 JSON without duplicate or nonfinite fields") from None
    return receipt


def _same_json(left, right):
    """JSON equality that does not treat booleans as integer parameters/counts."""
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(right, sort_keys=True, allow_nan=False)


def _digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _receipt(content):
    receipt = _strict_json(content)
    if not isinstance(receipt, dict) or set(receipt) != _RECEIPT_FIELDS:
        raise PubMedError("PubMed receipt has missing or unsupported fields")
    if type(receipt["schema_version"]) is not int or receipt["schema_version"] != 1 or receipt["source"] != "PubMed" or receipt["adapter"] != "lit-rev-engine.pubmed.v1":
        raise PubMedError("Unsupported PubMed receipt schema/source/adapter")
    if receipt["complete"] is not True:
        raise PubMedError("PubMed capture receipt must be complete")
    if not isinstance(receipt["query"], str) or not receipt["query"].strip() or not isinstance(receipt["query_translation"], str):
        raise PubMedError("PubMed receipt requires string query and translation")
    if not isinstance(receipt["sort"], str) or receipt["sort"] not in {"pub_date", "relevance"}:
        raise PubMedError("PubMed receipt has unsupported sort")
    if not isinstance(receipt["filters"], dict):
        raise PubMedError("PubMed receipt filters must be an object")
    _filters(receipt["filters"])
    times = []
    for field in ("started_at", "searched_at", "completed_at"):
        if not isinstance(receipt[field], str):
            raise PubMedError("PubMed receipt timestamps must be UTC ISO strings")
        try:
            stamp = datetime.fromisoformat(receipt[field])
        except ValueError:
            raise PubMedError("PubMed receipt timestamps must be UTC ISO strings") from None
        if stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
            raise PubMedError("PubMed receipt timestamps must use UTC")
        times.append(stamp)
    if not times[0] <= times[1] <= times[2]:
        raise PubMedError("PubMed receipt timestamps are not chronological")
    for field in ("reported_count", "fetched_count"):
        if type(receipt[field]) is not int or not 0 <= receipt[field] <= 10000:
            raise PubMedError("PubMed receipt counts must be nonnegative integers within the API limit")
    pmids = receipt["pmids"]
    if not isinstance(pmids, list) or any(not isinstance(pmid, str) for pmid in pmids):
        raise PubMedError("PubMed receipt PMIDs must be an ordered string list")
    try:
        normalized = [normalize_pmid(pmid) for pmid in pmids]
    except ValueError:
        raise PubMedError("PubMed receipt contains invalid PMID") from None
    if normalized != pmids or None in normalized or len(set(pmids)) != len(pmids):
        raise PubMedError("PubMed receipt requires unique normalized PMIDs")
    if receipt["reported_count"] != len(pmids) or receipt["fetched_count"] != len(pmids):
        raise PubMedError("PubMed receipt counts do not match complete PMID membership")
    if not isinstance(receipt["warnings"], list) or any(
        not isinstance(warning, dict) or set(warning) != {"code", "message"}
        or not isinstance(warning["code"], str) or not isinstance(warning["message"], str)
        for warning in receipt["warnings"]
    ):
        raise PubMedError("PubMed receipt warnings must be ordered code/message objects")
    history = receipt["history"]
    if not isinstance(history, dict) or set(history) != {"webenv", "query_key"} or any(value is not None and not isinstance(value, str) for value in history.values()):
        raise PubMedError("PubMed receipt history has invalid fields")
    if pmids and any(not value or not value.strip() for value in history.values()):
        raise PubMedError("Nonempty PubMed receipt requires history tokens")
    if receipt["records_file"] != "records.xml" or not _digest(receipt["records_sha256"]):
        raise PubMedError("PubMed receipt has invalid records file/hash")
    requests = receipt["requests"]
    if not isinstance(requests, list) or not requests:
        raise PubMedError("PubMed receipt requires ordered request metadata")
    for index, request in enumerate(requests):
        if not isinstance(request, dict) or set(request) != _REQUEST_FIELDS or not isinstance(request["params"], dict) or not _digest(request["response_sha256"]):
            raise PubMedError("PubMed receipt request has missing or invalid fields")
        endpoint = "esearch.fcgi" if index == 0 else "efetch.fcgi"
        name = "search.xml" if index == 0 else f"batches/{index:04d}.xml"
        if request["endpoint"] != endpoint or request["response_file"] != name:
            raise PubMedError("PubMed receipt request endpoint/path/order is invalid")
    return receipt


def _element_content(element, include_tail=False):
    """Compare XML content including mixed text, attributes and child order."""
    return (
        element.tag, tuple(sorted(element.attrib.items())), element.text,
        tuple(_element_content(child, True) for child in element),
        element.tail if include_tail else None,
    )


def validate_pubmed_artifacts(artifacts):
    """Verify one immutable byte snapshot; never open files or make requests."""
    if not isinstance(artifacts, dict) or any(not isinstance(name, str) or not isinstance(content, bytes) for name, content in artifacts.items()):
        raise PubMedError("PubMed artifacts must map relative names to bytes")
    if "receipt.json" not in artifacts:
        raise PubMedError("PubMed capture is missing receipt.json")
    receipt = _receipt(artifacts["receipt.json"])
    required = {"receipt.json", "records.xml", *(request["response_file"] for request in receipt["requests"])}
    if set(artifacts) != required:
        raise PubMedError("PubMed artifact mapping contains missing or unsupported files")
    for request in receipt["requests"]:
        if hashlib.sha256(artifacts[request["response_file"]]).hexdigest() != request["response_sha256"]:
            raise PubMedError("PubMed response artifact hash mismatch")
    combined = artifacts["records.xml"]
    if hashlib.sha256(combined).hexdigest() != receipt["records_sha256"]:
        raise PubMedError("PubMed combined records hash mismatch")
    count, pmids, translation, history, warnings = _search_membership(artifacts["search.xml"])
    if (receipt["reported_count"], receipt["pmids"], receipt["query_translation"], receipt["history"], receipt["warnings"]) != (count, pmids, translation, history, warnings):
        raise PubMedError("PubMed receipt contradicts the saved ESearch response")
    search_params = {"db": "pubmed", "term": receipt["query"], "retmode": "xml", "retstart": 0, "retmax": 10000, "usehistory": "y", "sort": receipt["sort"], **receipt["filters"]}
    if not _same_json(receipt["requests"][0]["params"], search_params):
        raise PubMedError("PubMed ESearch parameters contradict receipt or contain unsupported fields")
    found, offset = {}, 0
    for request in receipt["requests"][1:]:
        params = request["params"]
        if set(params) != {"db", "id", "retmode"} or params.get("db") != "pubmed" or params.get("retmode") != "xml" or not isinstance(params.get("id"), str):
            raise PubMedError("PubMed EFetch parameters contain unsupported fields")
        batch = params["id"].split(",")
        if not 1 <= len(batch) <= 200 or batch != pmids[offset:offset + len(batch)]:
            raise PubMedError("PubMed EFetch batches do not partition captured PMIDs in order")
        found.update(_validated_batch(artifacts[request["response_file"]], batch))
        offset += len(batch)
    if offset != count or set(found) != set(pmids):
        raise PubMedError("PubMed capture has incomplete EFetch membership")
    root = _parse_xml(combined, "Combined PubMed XML")
    if root.tag != "PubmedArticleSet" or len(root) != count or (root.text or "").strip() or any((element.tail or "").strip() for element in root):
        raise PubMedError("Combined PubMed XML must be the complete ordered PubmedArticleSet")
    if any(_element_content(element) != _element_content(found[pmid]) for element, pmid in zip(root, pmids)):
        raise PubMedError("Combined PubMed XML content differs from its original batch records")
    try:
        records = load_records_bytes(combined, "pubmed_xml", source_name="records.xml")
        if [normalize_pmid(record.pmid) for record in records] != pmids:
            raise ValueError
    except ValueError:
        raise PubMedError("Combined PubMed XML failed ordered importer replay") from None
    return {"receipt": receipt, "records": records}


def _read_capture(directory):
    root = Path(directory).absolute()
    if root.is_symlink() or not root.is_dir():
        raise PubMedError("PubMed capture must be an existing nonsymlink directory")
    root = root.resolve()

    def read(name):
        path = root / name
        for component in (path, *path.parents):
            if component == root:
                break
            if component.is_symlink():
                raise PubMedError("PubMed declared artifact paths must not be symlinks")
        try:
            if not path.resolve(strict=True).is_relative_to(root) or not path.is_file():
                raise PubMedError("PubMed artifact path escapes capture directory or is not a file")
            return path.read_bytes()
        except OSError:
            raise PubMedError("PubMed declared artifact is missing or unreadable") from None

    receipt_bytes = read("receipt.json")
    receipt = _receipt(receipt_bytes)
    artifacts = {"receipt.json": receipt_bytes}
    names = ["records.xml", *(request["response_file"] for request in receipt["requests"])]
    for name in names:
        artifacts[name] = read(name)
    validated = validate_pubmed_artifacts(artifacts)
    return root, artifacts, validated


def verify_pubmed_capture(directory):
    """Read declared files once and validate their captured byte snapshot."""
    root, _, validated = _read_capture(directory)
    return {"directory": str(root), "xml_file": str(root / "records.xml"), "receipt_file": str(root / "receipt.json"), "receipt": validated["receipt"]}


def import_pubmed_capture(store, project_id, directory, idempotency_key=None):
    """Persist verified records and exact source bytes in one ledger transaction."""
    root, artifacts, validated = _read_capture(directory)
    receipt = validated["receipt"]
    spec = SearchRunSpec(
        source="PubMed", query=receipt["query"], searched_at=receipt["searched_at"],
        filters=receipt["filters"], import_format="pubmed_xml", source_file=str(root / "records.xml"),
        source_sha256=receipt["records_sha256"], reported_count=receipt["reported_count"], execution=receipt,
    )
    return store.import_records(project_id, spec, validated["records"], idempotency_key, artifacts=artifacts)
