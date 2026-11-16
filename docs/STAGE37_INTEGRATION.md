# Stage 37 integration branch

Branch `claude/stage37-integration`, built on
`stage37/master-acceptance-interoperability-spec` @ `2f9af71` (the owner's PR #71).
Every feature branch is merged with a merge commit (`git merge --no-ff`); no
branch was rebased, squashed or force-pushed, and no feature branch was changed.

## 1. Merge graph

First-parent history, oldest first. "Parents" are the first parent (the
integration branch before the merge) and the second (the branch head).

| # | Commit | Parents | Merged branch @ head | What it brings |
|---|---|---|---|---|
| 1 | `32c2223` | `2f9af71`, `0a7c742` | `claude/stage37-0b` @ `0a7c742` | Stage 37.0b and its review fixes |
| 2 | `cdded4e` | `32c2223`, `7f35f0a` | `claude/stage37-methods` @ `7f35f0a` | path models, linear model, in-house Cronbach's α; pingouin to the dev lock |
| 3 | `1dceef3` | `cdded4e`, `89e9e5a` | `claude/stage37-export` @ `89e9e5a` | data export (.xlsx, .csv, .sav), Results workbook, reproducibility bundle; pyreadstat |
| 4 | `82be61a` | `1dceef3`, `16a0bdc` | `claude/stage37-rag` @ `16a0bdc` | research library, library questions, packaged FTS5 self-test |
| – | `9218d7a` | `82be61a` | – | CI: Windows path filters for the Stage 37 modules |

All four branches start at `2f9af71` (each `git merge-base` with the base is `2f9af71`).

## 2. Conflicts and how they were resolved

The rule for every conflict was to keep both sides' content.

| Merge | File | Conflict | Resolution |
|---|---|---|---|
| 2, 3, 4 | `workspace_text.py` | Each branch appended its own `T.update({...})` block after the same line. | Both blocks were kept: the earlier merge's block, then the incoming one. No key is defined in both. A three-way check (`T`, `LABELS`, `PLURALS` of the merged module = base + every branch's changes, with no key changed by two branches) is clean after each merge. |
| 3 | `requirements.txt` | Methods removed pingouin and its dependencies; export added pyreadstat. | Not hand-merged. Both locks were regenerated (§3). |
| 3 | `tests/fixtures/stage37/README.md` | Each branch rewrote the status line. | One integration status line, then the methods increment, then the export increment. The stale "RAG and mediation/moderation are not implemented" was dropped. |
| 3, 4 | `tools/windows_gui_e2e.py` | Each branch appended a 19th journey: its docstring entry, its code after `report-composition` and its `JOURNEYS` entry. | Everything kept, in merge order. No top-level name is defined twice (checked; pyflakes clean). |
| 3, 4 | `tests/test_stage368_review_journeys.py` | Each branch changed the count of journeys (19, or ≥ 18). | The exact combined order is asserted once: `STAGE37_JOURNEYS` after the 18 RC journeys. The branch tests check only their own journey's place: `test_stage37_journey.py` (index 18), and `test_stage37_export_journey.py` / `test_stage37_library_journey.py` (after the 18). |

Journey order after part 1: the 18 RC journeys, then `stage37-hypothesis`,
`export-data`, `research-library` (21).

Auto-merged files changed by more than one branch were reviewed as well:
`project_session.py`, `project_store.py`, `research_workflow.py`,
`workspace_analyze.py`, `workspace_projects.py` and `workspace_shell.py`. The
changes are in different functions. `project_store.SCHEMA_VERSION` stays 6.

A follow-up adjustment that is not a textual conflict: `tests/test_stage37_dependency.py`
(export) expected the export branch's 50 runtime pins. It now expects the integrated 42 and checks that pingouin is not in the runtime lock.

## 3. Locks

The inputs were resolved to the union of both intents. `requirements.in`
(auto-merged) has no pingouin and adds `pyreadstat>=1.3,<2`.
`requirements-dev.in` is the methods version, with pingouin as the test-only oracle.

Both locks were regenerated once with uv 0.11.32, using the exact header commands:

    uv pip compile requirements.in --universal --python-version 3.12 --generate-hashes --exclude-newer 2026-11-09T19:00:00Z -o requirements.txt
    uv pip compile requirements-dev.in -c requirements.txt --universal --python-version 3.12 --generate-hashes --exclude-newer 2026-11-09T19:00:00Z -o requirements-dev.txt

The methods runtime lock was in place as uv's preference file, so the pins the methods branch had were kept.

| Lock | vs. methods (`7f35f0a`) | vs. export (`89e9e5a`) | vs. base (`2f9af71`) |
|---|---|---|---|
| `requirements.txt` (42 pins) | + pyreadstat 1.3.7. Every other version, marker and hash is identical. The only other text change is narwhals' "via" comment, which now names pyreadstat too. | − cloudpickle 3.1.2, joblib 1.6.0, pandas-flavor 0.8.1, pingouin 0.7.0, scikit-learn 1.9.1, seaborn 0.13.2, tabulate 0.10.0, xarray 2026.9.0. pyreadstat's 26 hashes are identical, including the cp312 win_amd64 wheel `7b65bd28…4609`. | − the eight above, + pyreadstat 1.3.7 |
| `requirements-dev.txt` (82 pins) | byte-identical | + pingouin 0.7.0 and the 23 packages it brings, at the runtime lock's versions | as vs. export |

Tool checks, in a fresh venv with both locks installed by hash:

- `tools/build_toolchain.py identity --strict`: the host packages match the locks exactly (expected 88, found 88, 0 missing, 0 extra, 0 mismatched). The only deviation is the host Python: 3.12.3 here, while the lock says 3.12.16, which uv could not provide in this container. That deviation comes from the environment, not from the lock.
- `tools/build_sbom.py`: 84 components. pyreadstat 1.3.7 is listed as Apache-2.0, with ReadStat (MIT) inside it. pingouin is gone. The copyleft list (OCR DLLs and certifi only) is unchanged.
- `docs/STAGE368_BUILD_LOCK.md`: the counts were updated (42 runtime and 82 development packages, the package table, the SBOM's Python packages).

## 4. CI workflows

- `python-tests.yml`: the methods change is kept. The unit job installs
  `requirements.txt` and `requirements-dev.txt`, so the pingouin oracle runs, and
  the pruned-runtime job keeps the runtime lock alone.
- `windows-gui-e2e.yml`: export's path triggers are kept. Commit `9218d7a` adds the
  modules the Stage 37 journeys run:
  - 0b: `research_workflow.py`, `research_report.py`, `interpretation_docx.py`, `report_docx.py`.
  - methods: `cronbach.py`, `linear_model.py`, `process_*.py`, `reliability.py`,
    `item_diagnostics.py`, `correlation.py`, `batch_correlation.py`, `analysis_runs.py`,
    `result_store.py`, `interpretation_*.py`.
  - export: `data_preparation.py`.
  - rag: `research_library.py`, `library_ask.py`, `ai_*.py`, `tests/library_fixtures.py`.
- `windows-package.yml`: adds the new top-level modules bundled into the program, plus
  `reliability.py`, `research_workflow.py` and `research_report.py`. The packaged
  self-test runs the in-house α and the FTS5 search.
- `workspace_export.py` and `workspace_library.py` were already covered by `workspace_*.py`.
- Every new top-level module of the four branches is now in a Windows path filter (checked by listing the `*.py` files missing at `2f9af71`).

## 5. Semantic checks (after each merge)

New test module: `tests/test_stage37_integration.py`, which covers the seams between branches.

| Check | How | Result |
|---|---|---|
| Locale | `tools/locale_audit.py` after every merge | missing 0, placeholder 0 each time. "identical" rose from 0 to 15 with methods: abbreviations SE, SMD and VIF in `process_text.TEXT`, branch content, not caused by the merge. |
| Project format 6, append-only records | `SCHEMA_VERSION = 6` unchanged. 0b's store tests (`protocol_records_no_replace` trigger, update/delete refused) pass on every merged tree. Export keeps metadata in existing format-6 columns, and the library is a separate database in the project folder. | ok |
| K1 confirmation scopes (0b × methods) | `ConfirmationScopeTests`: a conditional-process task's confirmations make 0b's design step ready for Model 7 only. Moving to Model 14 (methods' option-bound scope) or to another mediator clears it. Both branches' own K1 tests pass. | ok |
| Word report (0b × methods) | `WordReportTests`: through the real handlers, H1's correlations plus a Model 4 mediation. The report holds "H1 (primary): …", "result current, in this report.", the evidence table (H1 × 1 result), "Mediation (PROCESS-equivalent Model 4)" and the indirect-effect table. | ok |
| Results workbook (export × methods × 0b) | `ExportTests`: Results → *Save*. The workbook has 4 sheets. Methods' `indirect:m0` and its CI are unrounded, equal to the engine. Provenance carries 0b's hypothesis snapshot (H1's id) and the bootstrap seed and resamples. | ok |
| Bundle report (export × 0b) | the reproducibility bundle's `report/*.docx` holds the hypothesis rows and the path model; the manifest has 2 analyses | ok |
| Library backup choice × export bundle | `LibraryExportTests`: with the library chosen to travel, the data bundle contains nothing of the library while the `.sra` backup contains `project/library/backup.json`. Exporting leaves the backup choice, and changing the backup choice leaves the remembered export choices. | ok |
| Packaged-style self-test | `analysis_selftest.py` on the merged tree: ok, 0 errors. Steps include `alpha` (in-house) and `research_library` (FTS5 and trigram available). | ok |

Targeted tests after each merge (integrated venv; the full suite was not run in part 1):

| After | 0b set | methods set | export set | rag set | common* |
|---|---|---|---|---|---|
| merge 1 | 240 OK (with common) | – | – | – | – |
| merge 2 | 240 OK (with common) | 192 OK | – | – | 3 (integration) OK |
| merge 3 | 174 OK | 192 OK | 84 OK | – | 66 OK |
| merge 4 | 174 OK | 192 OK | 84 OK | 116 OK | 67 OK |

\* common: `test_stage368_review_journeys`, `test_build_lock`, `test_locale_audit`,
`test_localized_guides_apa7` and `test_stage37_integration`. Each branch set has the
branch's new and changed test modules. 0b: `test_stage37_*` of 0b and
`test_workspace_journey_strip`. methods: `test_cronbach`, `test_linear_model`,
`test_process_*`, `test_spearman_floor`, `test_stage37_fixture_v2`,
`test_stage37_master_acceptance`, `test_stage37_methods_fixes`,
`test_distribution_tools`, `test_repeated`, `test_stage36_scales`,
`test_workspace_foundations` and `test_workspace_journeys`. export:
`test_stage37_csv_guard`, `test_stage37_dependency`, `test_stage37_export*` and
`test_app_preferences`. rag: `test_library_*`, `test_research_library`,
`test_stage37_ai_rows`, `test_stage37_library_journey` and `test_workspace_library`.
