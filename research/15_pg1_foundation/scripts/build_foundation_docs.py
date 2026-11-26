"""Generate the safe text-only bootstrap; private paths/data stay outside repository."""
from pathlib import Path
import csv,json
ROOT=Path(__file__).resolve().parents[1];REPO=ROOT/'repository'
def main():
 artifacts=json.loads((ROOT/'audit/baseline_registry_private.json').read_text(encoding='utf-8'))['artifacts']
 docs={
 'project_charter.md':'''# Project charter

The system studies the last exterior pedestrian approach to a known registered building entrance or an explicitly outside-only target. Inputs are real surrounding map objects, known identity, legal start and task semantics. Outputs distinguish native paths, mapped-face-derived segments, conditional assumptions and failure.

Two tracks run together: A improves existing semantic constraints/line-area fusion/full-face/F0-F1/global portal choice on exposed development data; B audits map fidelity, independent datasets, reference quality and spatial leakage. Neither a drawn line nor a registered entrance establishes present public entry.

Initial execution is Phase0 plus Phase1/2 and bounded TrackA continuity. No new entrance generation, model training, paid service, broad parameter sweep or blind evaluation is authorized. New source discovery is small, licensed preview/schema inspection, not a city-wide dataset acquisition.

G0 requires exact public-file approval before first push; G1 requires natural-language map review; G2 requires source/license/contract and spatial split approval. The parent remains FOUNDATION until those decisions; it is not PASS merely because files or a ZIP exist.
''',
 'research_overview.md':'''# Research overview

Phase0 is bootstrap/handover; the five research phases are:1 map fidelity,2 dataset discovery,3 continued development,4 validation/selection/freeze,5 blind evaluation and operational prototype. The current round starts1 and2 in parallel and permits bounded existing-method development; phases4/5 are not started.

Map fidelity traces raw source → imported semantics → routing representation → rendering. Vehicle-road context is distinct from admissible pedestrian edges; centerlines are not road surfaces. Missing source fields, filters, abstractions, clipped coverage and weak visual styling require different explanations.

Historical source completion and exact interfaces improved local mechanism queries but did not improve four fixed business routes. Retain that negative result. Six current target buildings have shared source objects and cannot be treated as six independent geographic test groups.

G0 repository/handover; G1 map review; G2 dataset/split review; G3 validation method freeze; G4 blind/prototype review. A public candidate shown during discovery is exposed and cannot simply be relabeled a fresh blind case.
''',
 'research_decisions.md':'''# Decisions and pending approvals

2026-11-12 — User selected the personal public repository. Do not use the legacy organization's remote for this goal; do not alter old remotes or staging.

2026-11-12 — First push is explicitly withheld pending approval of the exact file list and release audit. Local commits are preparation; remote synchronization has not happened.

2026-11-12 — Preserve all historical final/failed artifacts. Package-internal preseal PENDING is interpreted with its SHA-bound outside final receipt, not silently edited. An ambiguously named missing WALKABILITY-R1 is not reconstructed or renamed from the distinct NORTH-ACCESS-R1.

2026-11-12 — Continue bounded cost-interface development on the already exposed B3 graphs, with no new constraint family or tuning. Keep scalar construction if the batch candidate has no justified gain. No route-cost improvement is presumed.

2026-11-12 — Source discovery permits at most three providers and small, capped preview/schema reads; preserve empty/timeout/capped responses. A same-window CRS-interface repair is a recorded bounded engineering correction, not permission to expand geography. Actual request counts/bytes belong in the private audit.

Pending: G0 first-public-push and software license choice; G1 visual fidelity acceptance; G2 defensible candidate groups/independent curation and future acquisition scope. No Blind split is frozen.
''',
 'project_status.md':'''# Project status

Parent: SMART-CITY-WALKABILITY-FOUNDATION-PG1. State: FOUNDATION / WAIT_G0_G1_G2_REVIEW after the initial deliverable. The parent is not complete and no later validation or blind phase is authorized.

Local repository bootstrap is isolated from old Git workspaces. First public push: NOT_APPROVED_NOT_PERFORMED. Remote baseline: EMPTY_REPOSITORY. Base commit is NONE for the first local root; final local commit and branch are recorded in the external round binding to avoid self-hash cycles.

The private review packet includes actual historical hashes, six-source map lineage and real visualizations, capped source discovery, development probe invocations, independent checks and explicit unknowns. It is not automatically a public-data release.

Author checks, separate independent technical review, later GPT review, natural-language user acceptance and public-release approval remain distinct states. Old user observations and unrelated screenshot request bindings are not promoted by this foundation work.
''',
 'dataset_registry.md':'''# Dataset registry and contracts

Development: the six frozen Shanghai scene extracts from PILOT-R3, traceable through later fixed baselines. All are exposed. Only two target buildings have registered doors in the current prototype; the other four are map-information/constraint development scenes, not invented entrance tasks.

Geographic grouping is by complete building/site, overlapping source bounds, shared native ways/relations and dependent street network. Six building IDs do not imply six independent groups. Do not random-split queries, entrances or adjacent clips.

Discovery: municipal vector/OSM-family candidates are dimension-audited for building, registered door, sidewalk/crossing, pedestrian area, restrictions and reference independence. A licensed building footprint is not a verified entrance or walkable-space label. GOLD/SILVER/BRONZE must be task-specific; unknown fields are not zero.

Current bounded previews and maps stay in the local evidence packet; detailed coordinates/raw extracts are excluded from this bootstrap. Exposed discovery candidates are not blind. Validation/Blind proposals await G2; hidden reference curation and access logging must precede any future blind claim.
''',
 'methodology_registry.md':'''# Method registry

Current families: source-complete pedestrian areas; exact line/area and area/area interfaces; separately labelled conditional seams; full legal face interiors with holes/obstacles; bounded30m door-side conditional space; joint graph route choice to fixed registered endpoints.

Frozen F0 cost equals length; F1 adds one further unit of penalty to hypothesis length (hypothesis length is therefore charged twice). Same area/nodes/edges/interfaces across modes; a lower cost is not a probability of safety. Keep unknown access/level distinct from explicit conflicts, and never open grass/carriageways because of absent labels.

TA-PG1-01 tests only scalar versus batched minimum-over-parallel-option cost construction on fixed exposed B3 graphs. Fresh solve results and cost/provenance certificates are separate from inherited source admission. No new algorithm mechanism, geographic generalization or physical-navigation gain is claimed.

Research queue: source-semantic/render fidelity; source-complete interfaces; reference-independent validation; endpoint attachment transparency; cold-preprocessing efficiency. Each candidate needs a specific failure hypothesis, same-input comparison, finite budget, constraint integrity, ablation and a recorded accept/reject. Unmarked entrance generation is deferred.
''',
 'round_delivery_protocol.md':'''# Round delivery protocol

Canonical remote: gubingren0409/saomazhihuichengshilaoshishigeshibi. Initial local branch: codex/pg1-foundation-g0-g2. The first root has Base Commit NONE_EMPTY_REMOTE. Record Final Commit SHA, tree SHA and a source-file manifest outside that commit; do not insert a commit's own SHA into its contents.

Each review ZIP binds exactly that local final commit and source tree. Include the audited source snapshot, exact code/config/data hashes, machine outputs, true maps, failed runs, limitations and independent replay receipt. Large and restricted baselines remain external SHA-bound dependencies. The packet is private review material, not an approved public upload.

Before initial push: inspect exact proposed files, staged inventory/diff, secrets, sensitive-coordinate, license and generated/large-file audit. Wait for the user's explicit approval. Proposed initial remote target is main only for the exact approved bootstrap commit. No force push, PR merge or remote mutation is authorized by this preparation.

After approved bootstrap use dedicated round branches and reviewed PRs; main is the integration line. Rebuild/replay any changed final ZIP. Outside postseal receipts bind ZIP SHA to avoid a circular hash; a preseal status must not be silently rewritten inside the fixed package.
''',
 'public_release_audit.md':'''# Proposed public release boundary

Only the final exact file inventory may be approved. Candidate public content: new own source/tests, schemas, project charter/status/methodology and hash-only historical registry. Raw OSM/government extracts, candidate coordinates/maps, private screenshots, API responses, local absolute paths, old Git snapshots/indexes, old archives and caches are outside this release.

No legacy code is automatically relicensed. New-source license choice remains UNSPECIFIED_PENDING_USER; this bootstrap does not assign an open-source license on the user's behalf. GitHub public visibility alone is not a general redistribution license: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository

OSM-derived data/maps have separate attribution/ODbL obligations: https://www.openstreetmap.org/copyright and https://osmfoundation.org/wiki/Licence/Attribution_Guidelines . These do not replace municipal dataset-specific terms. No government or commercial-map raw data is included in the proposed public tree.

Machine audit records include per-file SHA/size, path/type rules, credential patterns, sensitive-coordinate/private-path checks and generated/large-file exclusions. An automated scan is not a proof of all legal rights; independent review and user release approval remain required. A file inventory is approval evidence, not permission to push.
'''}
 for name,text in docs.items():p=REPO/'docs'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
 fields=['artifact_id','canonical_reference','bytes','sha256','verification','role','source_commit','public_release']
 with(REPO/'docs/baseline_registry.csv').open('w',encoding='utf-8',newline='')as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
  for r in artifacts:w.writerow({k:('external-artifact:'+r['artifact_id']if k=='canonical_reference'else r.get(k,''))for k in fields})
 schema={'$schema':'https://json-schema.org/draft/2020-12/schema','title':'PG1 scene contract','type':'object','required':['scene_id','source_id','spatial_group_id','split','exposure','license_status','fields'], 'properties':{'scene_id':{'type':'string'},'source_id':{'type':'string'},'spatial_group_id':{'type':'string'},'split':{'enum':['DEVELOPMENT','UNASSIGNED_CANDIDATE','VALIDATION_APPROVED','BLIND_APPROVED']},'exposure':{'enum':['EXPOSED','UNEXPOSED_REFERENCE_BY_INDEPENDENT_CURATOR','UNKNOWN']},'license_status':{'enum':['AUDITED','RESTRICTED','UNKNOWN']},'fields':{'type':'object'}},'additionalProperties':False}
 (REPO/'schemas').mkdir(exist_ok=True);(REPO/'schemas/scene.schema.json').write_text(json.dumps(schema,indent=2),encoding='utf-8')
 for name,fields in [('sources',['source_id','url','retrieved_at','sha256','license','redistribution','coverage','limitations']),('experiments',['round_id','base_commit','final_commit','branch','data_hash','config_hash','code_hash','split','invocation_id','status']),('decisions',['decision_id','at','actor','evidence','decision','gate','approval_status'])]:
  (REPO/'schemas'/(name+'.schema.json')).write_text(json.dumps({'schema_version':'PG1-1','required_fields':fields,'unknown_policy':'UNKNOWN is not zero; preserve exact status and evidence'},indent=2),encoding='utf-8')
 print(json.dumps({'public_docs_written':len(docs)+1,'baseline_rows':len(artifacts),'schemas':4,'no_raw_data_copied':True}))
if __name__=='__main__':main()
