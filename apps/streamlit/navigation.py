"""Trusted presentation-only scroll behavior for workflow screen transitions."""

_RESET_SCRIPT = """<script>
(() => {
  // A previous passage link must not anchor the newly selected workflow screen.
  window.history.replaceState(
    window.history.state, "", window.location.pathname + window.location.search
  );
  const resetScroll = () => {
    document.querySelector('[data-testid="stMain"]')?.scrollTo({
      top: 0, left: 0, behavior: "instant"
    });
    window.scrollTo({top: 0, left: 0, behavior: "instant"});
  };
  resetScroll();
  // Run after the new headings have mounted and Streamlit has finished layout.
  requestAnimationFrame(() => requestAnimationFrame(resetScroll));
})();
</script>"""


def scroll_reset_html(revision: int) -> str:
    """A unique internal marker re-executes the static script on each transition.

    Never interpolate research questions, paper text, URLs or reviewer input into
    executable HTML. The caller supplies only an internal monotonic counter.
    """
    if type(revision) is not int or revision < 1:
        raise ValueError("Navigation revision must be a positive integer")
    return f'<span hidden data-lre-navigation-reset="{revision}"></span>' + _RESET_SCRIPT
