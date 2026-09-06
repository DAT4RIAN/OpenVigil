# Third-Party Notices

Last reviewed: 2026-08-13

This document records open-source projects studied as design and domain references for WindOps Multi-Agent Platform. It is informational: it does not replace the referenced license texts, constitute legal advice, grant a license to WindOps, or modify any third party's terms.

## Scope and clean-room statement

The projects below are **reference projects**, not vendored source dependencies of WindOps. Snapshots in the supplied local reference workspace were inspected for domain vocabulary, information architecture, interaction patterns and visual principles. WindOps was implemented independently from project requirements and its own TypeScript domain model.

No source code, stylesheets, assets, documentation text or other copyrightable implementation from these reference repositories was copied, adapted or incorporated into this repository. In particular, no AGPL-covered source from PyScada, NetBird Dashboard or Grafana was copied into WindOps. Reference to a project, product or trademark does not imply endorsement.

## Audited reference projects

| Project | Upstream | Locally audited revision | License observed at that revision | Pattern studied |
| --- | --- | --- | --- | --- |
| PyScada | [pyscada/PyScada](https://github.com/pyscada/PyScada) | [`8e2fc499b7f216fc3c0c0407842d9e18838f71cb`](https://github.com/pyscada/PyScada/commit/8e2fc499b7f216fc3c0c0407842d9e18838f71cb) | GNU AGPL v3 or later; see [LICENSE](https://github.com/pyscada/PyScada/blob/8e2fc499b7f216fc3c0c0407842d9e18838f71cb/LICENSE) and project metadata | SCADA asset hierarchy, devices, variables, history, alarms and monitoring concepts |
| OpenClaw Mission Control | [manish-raana/openclaw-mission-control](https://github.com/manish-raana/openclaw-mission-control) | [`fecdd3f285b7ece515526632f3ff46453b5a1c7c`](https://github.com/manish-raana/openclaw-mission-control/commit/fecdd3f285b7ece515526632f3ff46453b5a1c7c) | Apache License 2.0; see [LICENSE.txt](https://github.com/manish-raana/openclaw-mission-control/blob/fecdd3f285b7ece515526632f3ff46453b5a1c7c/LICENSE.txt) | Agent status, Mission/Task lifecycle, Kanban and activity timeline |
| NetBird Dashboard | [netbirdio/dashboard](https://github.com/netbirdio/dashboard) | [`bbfa2d3a795220680df5398b824036f43004f084`](https://github.com/netbirdio/dashboard/commit/bbfa2d3a795220680df5398b824036f43004f084) | GNU AGPL v3; see [LICENSE](https://github.com/netbirdio/dashboard/blob/bbfa2d3a795220680df5398b824036f43004f084/LICENSE) | Node/resource status, list-to-detail interaction, Drawer and topology concepts |
| next-shadcn-dashboard-starter | [Kiranism/next-shadcn-dashboard-starter](https://github.com/Kiranism/next-shadcn-dashboard-starter) | [`5f42819faf6d797a768b1aa1a2cb8c579b77ab3b`](https://github.com/Kiranism/next-shadcn-dashboard-starter/commit/5f42819faf6d797a768b1aa1a2cb8c579b77ab3b) | MIT License; see [LICENSE](https://github.com/Kiranism/next-shadcn-dashboard-starter/blob/5f42819faf6d797a768b1aa1a2cb8c579b77ab3b/LICENSE) | App Shell, dashboard composition, restrained cards/tables, theme and responsive layout |

## Grafana reference

[Grafana](https://github.com/grafana/grafana) was used only as a conceptual reference for time-series panels, thresholds, alert visualization, tooltips, time-range selection and dashboard grids. It was not present as a local checkout in the audited reference set, so **no local Grafana commit is claimed or pinned here**.

Grafana's default project license is [AGPL-3.0-only, with directory-specific exceptions documented upstream](https://github.com/grafana/grafana/blob/main/LICENSING.md). No Grafana source code, dashboard JSON, stylesheet, icon, asset or documentation text is included in WindOps; charts are independently implemented with the separately installed Apache ECharts package.

## Runtime and development dependencies

This notice intentionally does not enumerate every npm package or transitive dependency. Exact installed versions are recorded in `package.json` and `pnpm-lock.yaml`; each dependency remains subject to its own license and notices.

Release engineering should generate and archive a dependency license inventory or SPDX/CycloneDX SBOM separately, review bundled assets, and include any notices required by the versions actually shipped. That generated inventory supplements this reference-project record; it does not replace it.

## Trademarks and attribution

PyScada, OpenClaw Mission Control, NetBird, Grafana, next-shadcn-dashboard-starter and their associated names, logos and trademarks belong to their respective owners. WindOps does not use their logos and is not affiliated with, sponsored by or endorsed by those projects or maintainers.
