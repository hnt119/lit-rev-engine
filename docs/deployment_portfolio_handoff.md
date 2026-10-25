# Portfolio integration handoff — no live link yet

Read-only inspection of `hnt119/hnt119.github.io` on 23 October 2026 found commit
`3a03ea54b84d2658901522613641c054e5096637` on `main`. Reconfirm that repository's
current state before a later edit. No portfolio file, deployment setting, DNS or
Vercel project was changed in this task.

Exact existing files:

- Article: `src/content/projects/literature-review-engine.mdx`.
- Route: `src/app/projects/[slug]/page.tsx`, yielding
  `/projects/literature-review-engine/`; do not create a duplicate `/work/` page.
- Public static example: `src/components/LiteratureShowcase.tsx`, imported and
  rendered by the article. It uses explicitly synthetic fixture expectations,
  has no research API calls and must remain available without beta admission.
- Production: `.github/workflows/pages.yml`, on that repository's `main`, using
  static export and GitHub Pages. The separate `hnt119/website` Vercel backup is
  not this application and must not be repointed.

Repository references:
[article](https://github.com/hnt119/hnt119.github.io/blob/3a03ea54b84d2658901522613641c054e5096637/src/content/projects/literature-review-engine.mdx),
[showcase](https://github.com/hnt119/hnt119.github.io/blob/3a03ea54b84d2658901522613641c054e5096637/src/components/LiteratureShowcase.tsx),
[Pages workflow](https://github.com/hnt119/hnt119.github.io/blob/3a03ea54b84d2658901522613641c054e5096637/.github/workflows/pages.yml).

## Exact change after the hosted gate

No deployed application URL is known or verified. Do not insert a placeholder,
local test URL, guessed `onrender.com` hostname or beta code into the article.

After the application is deployed with authorization and the actual HTTPS URL
passes the deployment gate, add one short paragraph immediately before the
existing `<LiteratureShowcase />` in the article. Use the already verified URL as
the anchor target and the visible text **Open research workspace**. State before
the link that it is an **invite-only beta** and requires an invitation. Preserve
the existing example; optionally label its existing section **Try the example**
and give that section an internal anchor. Do not replace the static example with
an embedded private application, cookies, research data or provider credentials.

The change needs only that article. Do not duplicate backend code, change global
theme tokens, alter `/work/` compatibility redirects or replace hosting.

Use a portfolio feature branch and PR. The inspected Pages workflow runs:

```sh
pnpm install --frozen-lockfile
pnpm test:game
pnpm test:creatures
pnpm test:projects
pnpm check
pnpm build
pnpm check:export
```

Those portfolio commands were inspected, not executed in this application task.
Follow the repository's current instructions and obtain publication/merge
authorization. After Pages finishes, verify both the public example and the
application link from the published article in a fresh browser. Application
software/container checks are not proof that this website handoff was published.
