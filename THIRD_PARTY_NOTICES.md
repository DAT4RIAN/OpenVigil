# Third-Party Notices

Last reviewed: 2026-09-04

This document records open-source projects studied as design and domain references for OpenVigil Multi-Agent Platform. It is informational: it does not replace the referenced license texts, constitute legal advice, grant a license to OpenVigil, or modify any third party's terms.

## Scope and clean-room statement

The projects in the audited-reference table are **reference projects**, not vendored source dependencies of OpenVigil. Snapshots in the supplied local reference workspace were inspected for domain vocabulary, information architecture, interaction patterns and visual principles. OpenVigil was implemented independently from project requirements and its own TypeScript domain model. The separately documented EnergyFaultDetector submodule is the only source-level algorithm comparison oracle.

No source code, stylesheets, assets, documentation text or other copyrightable implementation from these reference repositories was copied, adapted or incorporated into this repository. In particular, no AGPL-covered source from PyScada, NetBird Dashboard or Grafana was copied into OpenVigil. Reference to a project, product or trademark does not imply endorsement.

## Audited reference projects

| Project                       | Upstream                                                                                            | Locally audited revision                                                                                                                                | License observed at that revision                                                                                                                         | Pattern studied                                                                        |
| ----------------------------- | --------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| PyScada                       | [pyscada/PyScada](https://github.com/pyscada/PyScada)                                               | [`8e2fc499b7f216fc3c0c0407842d9e18838f71cb`](https://github.com/pyscada/PyScada/commit/8e2fc499b7f216fc3c0c0407842d9e18838f71cb)                        | GNU AGPL v3 or later; see [LICENSE](https://github.com/pyscada/PyScada/blob/8e2fc499b7f216fc3c0c0407842d9e18838f71cb/LICENSE) and project metadata        | SCADA asset hierarchy, devices, variables, history, alarms and monitoring concepts     |
| OpenClaw Mission Control      | [manish-raana/openclaw-mission-control](https://github.com/manish-raana/openclaw-mission-control)   | [`fecdd3f285b7ece515526632f3ff46453b5a1c7c`](https://github.com/manish-raana/openclaw-mission-control/commit/fecdd3f285b7ece515526632f3ff46453b5a1c7c)  | Apache License 2.0; see [LICENSE.txt](https://github.com/manish-raana/openclaw-mission-control/blob/fecdd3f285b7ece515526632f3ff46453b5a1c7c/LICENSE.txt) | Agent status, Mission/Task lifecycle, Kanban and activity timeline                     |
| NetBird Dashboard             | [netbirdio/dashboard](https://github.com/netbirdio/dashboard)                                       | [`bbfa2d3a795220680df5398b824036f43004f084`](https://github.com/netbirdio/dashboard/commit/bbfa2d3a795220680df5398b824036f43004f084)                    | GNU AGPL v3; see [LICENSE](https://github.com/netbirdio/dashboard/blob/bbfa2d3a795220680df5398b824036f43004f084/LICENSE)                                  | Node/resource status, list-to-detail interaction, Drawer and topology concepts         |
| next-shadcn-dashboard-starter | [Kiranism/next-shadcn-dashboard-starter](https://github.com/Kiranism/next-shadcn-dashboard-starter) | [`5f42819faf6d797a768b1aa1a2cb8c579b77ab3b`](https://github.com/Kiranism/next-shadcn-dashboard-starter/commit/5f42819faf6d797a768b1aa1a2cb8c579b77ab3b) | MIT License; see [LICENSE](https://github.com/Kiranism/next-shadcn-dashboard-starter/blob/5f42819faf6d797a768b1aa1a2cb8c579b77ab3b/LICENSE)               | App Shell, dashboard composition, restrained cards/tables, theme and responsive layout |

## Grafana reference

[Grafana](https://github.com/grafana/grafana) was used only as a conceptual reference for time-series panels, thresholds, alert visualization, tooltips, time-range selection and dashboard grids. It was not present as a local checkout in the audited reference set, so **no local Grafana commit is claimed or pinned here**.

Grafana's default project license is [AGPL-3.0-only, with directory-specific exceptions documented upstream](https://github.com/grafana/grafana/blob/main/LICENSING.md). No Grafana source code, dashboard JSON, stylesheet, icon, asset or documentation text is included in OpenVigil; charts are independently implemented with the separately installed Apache ECharts package.

## CARE official scoring reference submodule

The official [AEFDI EnergyFaultDetector](https://github.com/AEFDI/EnergyFaultDetector) v0.6.2 source is an explicit test oracle, not a OpenVigil runtime dependency. It is retrieved through the mapped submodule `tmp/external/EnergyFaultDetector-v0.6.2` at immutable commit [`a338b6efb3a650536930c6e67247694071d2f63e`](https://github.com/AEFDI/EnergyFaultDetector/commit/a338b6efb3a650536930c6e67247694071d2f63e), Git tree `43c64cbe1119fb798f37d000e26657836845c912`, under the [MIT license at that revision](https://github.com/AEFDI/EnergyFaultDetector/blob/a338b6efb3a650536930c6e67247694071d2f63e/LICENSE). The license SHA-256 is `65f98b52eaf71a731ac8f878a0214896d63d6c0ffd4df6f486ca5e2440c2615f`.

CI executes only the official CARE score and criticality modules as a comparison oracle. Their SHA-256 identities are `122eaf43c5f6703b78e89a4273ad236ddb7b99f7598dcc44bc808e9476285078` and `2d593ef0474e5d38dd2cbca03fcf1de9f300f764c6305799c48b168481fb558e`. OpenVigil does not import the submodule at runtime or package it in its backend wheel/container; the verifier compares official boundary, status-freeze and earliness outputs with the independently maintained OpenVigil protocol and records both source-of-truth document hashes and a canonical evidence root.

## Runtime and development dependencies

This notice intentionally does not enumerate every npm package or transitive dependency. Exact installed versions are recorded in `package.json` and `pnpm-lock.yaml`; each dependency remains subject to its own license and notices.

Release engineering should generate and archive a dependency license inventory or SPDX/CycloneDX SBOM separately, review bundled assets, and include any notices required by the versions actually shipped. That generated inventory supplements this reference-project record; it does not replace it.

## CARE v6 benchmark data and derived artifacts

The repository's MIT `LICENSE` applies to OpenVigil code, not to CARE source data or CARE-derived data artifacts. CARE v6, “Wind Turbine SCADA Data For Early Fault Detection,” is attributed to Christian Gück and Cyriana M. A. Roelofs, Fraunhofer Institute for Energy Economics and Energy System Technology, and is published at [Zenodo DOI 10.5281/zenodo.15846963](https://doi.org/10.5281/zenodo.15846963) under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).

The recommended scholarly citation is: Gück, C.; Roelofs, C.M.A.; Faulstich, S. “CARE to Compare: A Real-World Benchmark Dataset for Early Fault Detection in Wind Turbine Data.” _Data_ 2024, 9, 138. [https://doi.org/10.3390/data9120138](https://doi.org/10.3390/data9120138).

Raw CARE data is not bundled in this repository. Any distributed derived artifact must retain attribution and the license link, identify changes and transformation versions, preserve source and artifact SHA-256 identities, and pass the external-distribution ShareAlike review described in `docs/runbooks/care-artifact-governance.md`.

## Trademarks and attribution

PyScada, OpenClaw Mission Control, NetBird, Grafana, next-shadcn-dashboard-starter and their associated names, logos and trademarks belong to their respective owners. OpenVigil does not use their logos and is not affiliated with, sponsored by or endorsed by those projects or maintainers.
