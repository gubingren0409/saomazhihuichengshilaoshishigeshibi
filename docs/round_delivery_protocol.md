# Round delivery protocol

Canonical remote: gubingren0409/saomazhihuichengshilaoshishigeshibi. Initial local branch: codex/pg1-foundation-g0-g2. The first root has Base Commit NONE_EMPTY_REMOTE. Record Final Commit SHA, tree SHA and a source-file manifest outside that commit; do not insert a commit's own SHA into its contents.

Each review ZIP binds exactly that local final commit and source tree. Include the audited source snapshot, exact code/config/data hashes, machine outputs, true maps, failed runs, limitations and independent replay receipt. Large and restricted baselines remain external SHA-bound dependencies. The packet is private review material, not an approved public upload.

Before initial push: inspect exact proposed files, staged inventory/diff, secrets, sensitive-coordinate, license and generated/large-file audit. Wait for the user's explicit approval. Proposed initial remote target is main only for the exact approved bootstrap commit. No force push, PR merge or remote mutation is authorized by this preparation.

After approved bootstrap use dedicated round branches and reviewed PRs; main is the integration line. Rebuild/replay any changed final ZIP. Outside postseal receipts bind ZIP SHA to avoid a circular hash; a preseal status must not be silently rewritten inside the fixed package.
