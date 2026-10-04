#!/usr/bin/env python3
"""Offline prospective compound truth integrity, independent raw reconstruction first."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def pin(path):
    raw=path.read_bytes()
    return {"sha256":digest(raw),"size_bytes":len(raw)}


def source_checker(directory):
    location=Path(directory)/"verify.py"
    spec=importlib.util.spec_from_file_location("qwen_source_original_xml_checker",location)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def verify(directory, reconcile=True):
    directory=Path(directory).resolve()
    manifest=read_json(directory/"manifest.json")
    require(manifest["schema_version"] == 1 and manifest["ticket"] == "KR4B" and manifest["split"] == 'confirmation', "Gold schema/ticket")
    acquisition=directory.parent/"qwen_components_confirmation_sources"
    require(manifest["source_manifest"]["file"] == "../qwen_components_confirmation_sources/manifest.json", "Exact acquisition scope")
    require(pin(acquisition/"manifest.json") == {k:manifest["source_manifest"][k] for k in ("sha256","size_bytes")}, "Acquisition manifest byte pins")
    original=source_checker(acquisition)
    acquired, rebuilt=original.verify(acquisition)
    require(set(manifest["files"]) == {"blocks.json","questions.json"}, "Exact gold file set")
    for name,expected in manifest["files"].items():
        require(not (directory/name).is_symlink() and pin(directory/name)==expected, "Gold file pin: "+name)
    blocks_data=read_json(directory/"blocks.json")
    questions_data=read_json(directory/"questions.json")
    require(blocks_data["schema_version"] == questions_data["schema_version"] == 1, "Canonical/truth schema")
    expected_blocks=[block for source in acquired["sources"] for block in rebuilt[source["id"]]]
    require(blocks_data["blocks"] == expected_blocks, "Every original path/text/ordinal/locator/block digest")
    require([s["id"] for s in manifest["sources"]] == [s["id"] for s in acquired["sources"]], "Selected source identities/order")
    for source,gold in zip(acquired["sources"],manifest["sources"]):
        require(gold == {"id":source["id"],"file":"../qwen_components_confirmation_sources/"+source["file"],"doi":source["doi"],"title":source["title"],"sha256":source["source_sha256"],"size_bytes":source["size_bytes"],"block_count":source["block_count"],"canonical_blocks_sha256":source["canonical_blocks_sha256"]}, "Gold-to-original source/byte binding")
        # Reconciliation follows the independent original-element checks above.
        if reconcile:
            repository=Path(__file__).resolve().parents[3]
            sys.path.insert(0,str(repository))
            from src.review.documents import parse_source_bytes
            parsed=parse_source_bytes((acquisition/source["file"]).read_bytes(),"jats_xml")
            require(parsed["parser_id"] == source["parser_id"], "Accepted parser ID reconciliation")
            canonical=[{"id":b["block_id"],"ordinal":b["ordinal"],"text":b["text"],"locator":b["locator"]} for b in rebuilt[source["id"]]]
            require(parsed["blocks"] == canonical, "Accepted parser original blocks reconciliation")
            require({k:v for k,v in parsed["parser_metadata"].items() if k!="python_version"} == {k:v for k,v in source["parser_metadata"].items() if k!="python_version"}, "Canonical rules versus preserved historical runtime")
    by_id={(b["source_id"],b["block_id"]):b for b in expected_blocks}
    sources=set(rebuilt)

    def validate_anchor(anchor,source_id):
        require(set(anchor)=={"source_id","block_id","source_path","block_sha256","start","end","quote"}, "Exact anchor schema")
        require(anchor["source_id"] == source_id, "Anchor question source binding")
        block=by_id.get((source_id,anchor["block_id"]))
        require(block is not None and anchor["source_path"] == block["source_path"] and anchor["block_sha256"] == block["sha256"], "Anchor original locator/hash")
        begin,end=anchor["start"],anchor["end"]
        require(type(begin) is int and type(end) is int and 0 <= begin < end <= len(block["text"]), "Half-open Unicode code-point offsets")
        require(isinstance(anchor["quote"],str) and block["text"][begin:end] == anchor["quote"], "Exact source Unicode quotation")
        return (source_id,block["block_id"])

    questions=questions_data["questions"]
    require(isinstance(questions,list) and len(questions)==8 and len({q["id"] for q in questions})==8, "Exactly eight unique fresh questions")
    and_total=0;method_result_total=0;alternatives=0;spans=0;context_spans=0;component_total=0
    for q in questions:
        require(set(q)=={"id","source_id","query","components","answerable","quantitative","category","expected_answer","necessary_and","support_sets","context_anchors","null_reason"}, "Exact question truth schema")
        require(isinstance(q["id"],str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}",q["id"]), "Safe question identity")
        require(len(q["query"].encode("utf-8"))<=2000, "Whole query UTF-8 limit")
        components=q["components"]
        require(isinstance(components,list) and len(components) in (2,3), "Every compound question has two or three request components")
        require(len({c["id"] for c in components})==len(components), "Unique component identities")
        for component in components:
            require(set(component)=={"id","query"} and isinstance(component["id"],str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}",component["id"]), "Exact safe component schema")
            require(isinstance(component["query"],str) and bool(component["query"].strip()) and len(component["query"].encode("utf-8"))<=2000, "Component request text limits")
        component_total+=len(components)
        require(q["source_id"] in sources and isinstance(q["query"],str) and bool(q["query"].strip()) and isinstance(q["category"],str) and bool(q["category"]), "Question/source/category")
        require(type(q["answerable"]) is bool and type(q["quantitative"]) is bool and type(q["necessary_and"]) is bool, "Truth flags")
        require(isinstance(q["support_sets"],list) and isinstance(q["context_anchors"],list), "Support/context collections")
        for anchor in q["context_anchors"]:
            validate_anchor(anchor,q["source_id"]); context_spans+=1
        distinct_counts=[]
        seen_alternatives=set()
        for alternative in q["support_sets"]:
            require(isinstance(alternative,list) and bool(alternative), "Nonempty sufficient alternative")
            identities={validate_anchor(a,q["source_id"]) for a in alternative}
            span_ids={(a["block_id"],a["start"],a["end"]) for a in alternative}
            require(len(span_ids)==len(alternative), "No duplicate quote spans in sufficient set")
            alternative_key=tuple(sorted(span_ids))
            require(alternative_key not in seen_alternatives, "No duplicate sufficient alternatives")
            seen_alternatives.add(alternative_key)
            distinct_counts.append(len(identities)); alternatives+=1; spans+=len(alternative)
        necessary_and=bool(distinct_counts) and min(distinct_counts)>=2
        require(q["necessary_and"] == necessary_and, "AND across every alternative needs distinct canonical blocks")
        and_total+=necessary_and
        method_result=bool(q["support_sets"]) and all(any("/body[1]/sec[2]/" in a["source_path"] for a in z) and any("/body[1]/sec[3]/" in a["source_path"] for a in z) for z in q["support_sets"])
        method_result_total+=method_result
        if q["answerable"]:
            require(bool(q["support_sets"]) and q["quantitative"] and isinstance(q["expected_answer"],str) and bool(re.search(r"\d",q["expected_answer"])) and q["null_reason"] is None, "Quantitative positive truth")
        else:
            require(q["support_sets"]==[] and q["expected_answer"] is None and q["quantitative"] is False and isinstance(q["null_reason"],str) and bool(q["null_reason"].strip()) and bool(q["context_anchors"]), "Article-scoped null/context distinction")
    counts={"questions":len(questions),"answerable":sum(q["answerable"] for q in questions),"nulls":sum(not q["answerable"] for q in questions),"quantitative":sum(q["quantitative"] for q in questions),"necessary_and":and_total,"necessary_methods_results_and":method_result_total,"components":component_total,"sources":len(sources),"canonical_blocks":len(expected_blocks),"main_tables":sum(s["main_table_count"] for s in acquired["sources"]),"support_alternatives":alternatives,"support_spans":spans,"context_spans":context_spans}
    require(counts==manifest["counts"] and counts["answerable"]==6 and counts["nulls"]==2 and counts["quantitative"]==6 and and_total>=4 and method_result_total>=4, "Fixed fresh pilot count floors")
    require(all(sum(q["source_id"]==source for q in questions)==4 for source in sources), "Four questions per fresh source")
    require("never scored as sufficient support" in manifest["semantics"]["context_anchors"], "Context/support scoring contract")
    require(manifest["prospective"]["rankings_observed"] == manifest["prospective"]["paid_inference_calls"] == 0, "No pre-truth ranking or paid calls")
    require(manifest["prospective"]["coordinator_confirmation_qa_blind"] is True, "Declared coordinator blindness")
    require(manifest["runtime_budget"] == {"candidate_own_blocks":20,"display_own_blocks":5,"batch_seconds":1800,"positive_coverage_floor_percent":85,"complete_positive_floor":4,"nonregression_comparators":["whole_question_lexical","whole_question_qwen","component_lexical"]}, "Fixed prospective budget and gates")
    # These two literal body section labels establish the Methods/Results prefix
    # used by the floor above; truth semantic sufficiency is checked independently.
    for source in acquired["sources"]:
        raw_root,_=original.independent_blocks((acquisition/source["file"]).read_bytes(),source["id"])
        sections=[e for e in raw_root.find("./body") if original.tag(e)=="sec"]
        require(original.inline(original.first(sections[1],"title")) in ("Methods","Materials and methods") and original.inline(original.first(sections[2],"title")) == "Results", "Original Methods/Results section identity")
    return counts


def self_test(directory):
    directory=Path(directory)
    original_manifest=read_json(directory/"manifest.json")
    original_questions=read_json(directory/"questions.json")
    original_blocks=read_json(directory/"blocks.json")
    mutations={
        "quote":lambda q,b,m:q["questions"][0]["support_sets"][0][0].update(quote="invented"),
        "Unicode begin":lambda q,b,m:q["questions"][0]["support_sets"][0][0].update(start=1),
        "Unicode end":lambda q,b,m:q["questions"][0]["support_sets"][0][0].update(end=2),
        "boolean offset":lambda q,b,m:q["questions"][0]["support_sets"][0][0].update(start=True),
        "block hash":lambda q,b,m:q["questions"][0]["support_sets"][0][0].update(block_sha256="0"*64),
        "source binding":lambda q,b,m:q["questions"][0]["support_sets"][0][0].update(source_id="unselected_source"),
        "locator":lambda q,b,m:q["questions"][0]["support_sets"][0][0].update(source_path="/invented[1]"),
        "whole canonical text":lambda q,b,m:b["blocks"][0].update(text=b["blocks"][0]["text"]+"changed"),
        "whole canonical ordinal":lambda q,b,m:b["blocks"][0].update(ordinal=100),
        "duplicate AND span":lambda q,b,m:q["questions"][0]["support_sets"].__setitem__(0,[q["questions"][0]["support_sets"][0][0]]*2),
        "singleton alternative under AND flag":lambda q,b,m:q["questions"][0]["support_sets"].append([q["questions"][0]["support_sets"][0][0]]),
        "empty sufficient alternative":lambda q,b,m:q["questions"][0]["support_sets"].append([]),
        "null context as support":lambda q,b,m:q["questions"][3].update(support_sets=[q["questions"][3]["context_anchors"]]),
        "null answer invented":lambda q,b,m:q["questions"][3].update(expected_answer="10%"),
        "missing null reason":lambda q,b,m:q["questions"][3].update(null_reason=None),
        "source hash rewritten":lambda q,b,m:m["sources"][0].update(sha256="0"*64),
        "acquisition pin":lambda q,b,m:m["source_manifest"].update(sha256="0"*64),
        "source file traversal":lambda q,b,m:m["sources"][0].update(file="../unselected_source.xml"),
        "counts":lambda q,b,m:m["counts"].update(questions=7),
        "one component":lambda q,b,m:q["questions"][0].update(components=q["questions"][0]["components"][:1]),
        "duplicate component":lambda q,b,m:q["questions"][0].update(components=[q["questions"][0]["components"][0]]*2),
        "unexpected component field":lambda q,b,m:q["questions"][0]["components"][0].update(expected_answer="leaked"),
        "invalid component identity":lambda q,b,m:q["questions"][0]["components"][0].update(id="unsafe/id"),
        "empty component request":lambda q,b,m:q["questions"][0]["components"][0].update(query=" "),
        "prior rankings":lambda q,b,m:m["prospective"].update(rankings_observed=1),
        "larger display budget":lambda q,b,m:m["runtime_budget"].update(display_own_blocks=6),
        "body AND floor":lambda q,b,m:m["counts"].update(necessary_methods_results_and=0),
    }
    with tempfile.TemporaryDirectory(prefix="qwen-gold-audit-") as tmp:
        top=Path(tmp); target=top/"qwen_components_confirmation_gold"; target.mkdir(); source=top/"qwen_components_confirmation_sources";source.mkdir()
        for name in ([s["id"]+".xml" for s in original_manifest["sources"]]+["manifest.json","verify.py"]):
            shutil.copyfile(directory.parent/"qwen_components_confirmation_sources"/name,source/name)
        for name,mutate in mutations.items():
            q=copy.deepcopy(original_questions);b=copy.deepcopy(original_blocks);m=copy.deepcopy(original_manifest)
            mutate(q,b,m)
            (target/"questions.json").write_text(json.dumps(q,ensure_ascii=False));(target/"blocks.json").write_text(json.dumps(b,ensure_ascii=False))
            m["files"]={n:pin(target/n) for n in ("blocks.json","questions.json")}
            (target/"manifest.json").write_text(json.dumps(m,ensure_ascii=False))
            try:
                verify(target)
            except (ValueError,KeyError,TypeError):
                continue
            raise AssertionError("Tamper accepted: "+name)
        # Consistently rewritten gold/source hashes cannot bypass archived raw pins.
        for name in ("questions.json","blocks.json","manifest.json"):
            shutil.copyfile(directory/name,target/name)
        raw=source/(original_manifest["sources"][0]["id"]+".xml");raw.write_bytes(raw.read_bytes()+b"\n")
        m=copy.deepcopy(original_manifest);m["sources"][0].update(sha256=digest(raw.read_bytes()),size_bytes=len(raw.read_bytes()))
        (target/"manifest.json").write_text(json.dumps(m))
        try:
            verify(target)
        except ValueError:
            pass
        else:
            raise AssertionError("Changed raw with rewritten gold source hash accepted")
        shutil.copyfile(directory.parent/"qwen_components_confirmation_sources"/(original_manifest["sources"][0]["id"]+".xml"),raw)
        historical=read_json(source/"manifest.json");historical["sources"][0]["parser_metadata"]["python_version"]="historical-runtime-record"
        (source/"manifest.json").write_text(json.dumps(historical))
        m=copy.deepcopy(original_manifest);m["source_manifest"].update(pin(source/"manifest.json"))
        (target/"manifest.json").write_text(json.dumps(m))
        verify(target)
    return len(mutations)+1


if __name__ == "__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--self-test",action="store_true")
    args=parser.parse_args();directory=Path(__file__).resolve().parent
    try:
        counts=verify(directory)
        print(f"PASS: {counts['questions']} questions, {counts['quantitative']} quantitative positives, {counts['necessary_and']} necessary AND, {counts['nulls']} article-scoped nulls; {counts['canonical_blocks']} blocks/{counts['support_spans']} support spans/{counts['context_spans']} context spans")
        if args.self_test:
            print(f"PASS: {self_test(directory)} gold tamper negatives; 1 historical-runtime positive")
    except Exception as exc:
        print(f"FAIL: {exc}",file=sys.stderr);sys.exit(1)
