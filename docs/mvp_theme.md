# MVP visual identity

The Literature Review Engine shares the paper, ink and olive identity of [hnt119.github.io](https://hnt119.github.io/). The actual portfolio repository was inspected before implementation on 20 October 2026: local clean `main` matched GitHub `main` at `64f04ed5ff3186e6340fc381e95a60ea6830bc6a`. The personal website was not edited or redeployed.

Source references:

- [Global CSS](https://github.com/hnt119/hnt119.github.io/blob/64f04ed5ff3186e6340fc381e95a60ea6830bc6a/src/styles/global.css): palette, Arial/monospace stacks, heading scale, editorial rows, link and focus treatment, responsive and reduced-motion rules.
- [Root layout](https://github.com/hnt119/hnt119.github.io/blob/64f04ed5ff3186e6340fc381e95a60ea6830bc6a/src/app/layout.tsx): 760px shell, 32px side padding, 24px on small screens.
- [Navigation](https://github.com/hnt119/hnt119.github.io/blob/64f04ed5ff3186e6340fc381e95a60ea6830bc6a/src/components/Navigation.tsx): understated links and explicit current state.

## Theme files

`apps/streamlit/theme/tokens.css` is plain, framework-independent CSS. It owns the required `--paper`, `--ink`, `--muted`, `--line`, `--accent` and `--mono` values and font stack. A future React/Next.js application can import it as global CSS without importing Streamlit or Python.

`apps/streamlit/theme/streamlit.css` adapts native Streamlit widgets to these tokens. `apps/streamlit/theme.py` loads the two local stylesheets; `app.py` injects them. `.streamlit/config.toml` mirrors the native widget palette so initial rendering and popup controls match. A focused presentation test checks the palette agreement.

The app uses Arial headings and reading text, small monospace metadata, generous whitespace, thin separators, and olive actions, selections, hover and keyboard focus. The portfolio's 42px landing heading, 15px reading text with 1.85 line height, and 19px section headings inform the scale. The app uses olive navigation hover as explicitly requested; the inspected portfolio currently uses ink for that hover. There are no decorative gradients, glow, glass effects or dashboard color tiles.

## Layout and accessibility

Discovery uses a 760px maximum frame. The research workspace widens to 1240px so evidence and judgment fields remain readable side by side. Widths include side padding. The sidebar remains native Streamlit navigation, with visible selected and keyboard-focus states.

Evidence follows this reading order:

1. Question and retrieval controls.
2. **Retrieved passages** on the left and **Record your judgments** on the right. Each passage and its matching decision/notes share a row; the next pair begins below the taller side, so variable quotation lengths cannot shift matching ranks out of alignment. The judgment heading has no rule beneath it.
3. **Verifiable source context** across the frame below both panels.
4. Evidence CSV and audit JSON downloads.

On narrow screens each pair stacks as passage, then its matching judgment, before the next passage. Native labels, forms, radio controls, keyboard operation and download behavior remain intact. Focus is visible, long identifiers and source text wrap, and reduced-motion preferences disable transitions and animations. Source quotations are escaped before adding the exact-match highlight; theme CSS never changes the stored text or source offsets.

The adapter targets native `data-testid` attributes and explicit container keys (`landing`, `workspace`, `evidence-columns`, `retrieved-passages`, `reviewer-judgments`, `source-context-section`). These are presentation hooks only. Recheck browser layout after Streamlit upgrades; API/domain tests alone cannot validate CSS selectors or visual alignment.

Workflow screen changes clear any earlier heading fragment and open the destination at the top. Ordinary reruns and explicit source-context links keep their normal scrolling behavior. `apps/streamlit/navigation.py` contains the trusted static script used with the pinned Streamlit 1.66 `st.html` API; only an internal integer counter is interpolated. Paper text, questions and reviewer input never enter executable HTML. This temporary browser behavior remains outside the research services.
