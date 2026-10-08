// @exec: {"yield_time_ms": 1000, "max_output_tokens": 2000}
// Run this code in functions.exec only AFTER the root agent freezes the release.
// Before running, store("hanjie_publication_authorization", {
//   manifest: "/tmp/hanjie-publication-manifest.json",
//   source_sha: "<reviewed immutable local release commit>",
//   message: "Complete ring manufacturing, automation and competition deliverables"
// });
// This file does not read credentials, use browser sessions, or invoke git push.

const authorization = load("hanjie_publication_authorization");
if (!authorization?.source_sha || !/^\/[A-Za-z0-9_./-]+\.json$/.test(authorization?.manifest || "")) {
  throw new Error("Root publication freeze authorization is missing");
}
function payload(result) {
  if (result.isError || !result.structuredContent) throw new Error(JSON.stringify(result));
  return result.structuredContent;
}
const workdir = "/workspace/scratch/3422b1ea02b9/repair-hanjie";
const read = await tools.exec_command({cmd: "cat " + authorization.manifest, workdir, max_output_tokens: 250000});
if (read.exit_code !== 0 || /truncated|omitted/.test(read.output)) throw new Error("Manifest was not read completely");
const manifest = JSON.parse(read.output);
if (manifest.source_local_commit_sha !== authorization.source_sha) throw new Error("Freeze SHA does not match the manifest");
if (manifest.repository_full_name !== "xianzai588/Hanjie" || manifest.branch_name !== "codex/complete-ring-deliverables") {
  throw new Error("Publication destination differs from the authorized repository and branch");
}
const head = payload(await tools.mcp__codex_apps__github_fetch_commit({
  repo_full_name: manifest.repository_full_name, commit_sha: manifest.branch_name
})).commit.sha;
if (head !== manifest.base_commit_sha) throw new Error("Remote branch moved; inspect it before rebuilding the release manifest");
const completed = new Set(load("hanjie_uploaded_blobs") || []);
let count = 0;
async function uploadBlob(blob) {
  if (!/^[0-9a-f]{40}$/.test(blob.sha)) throw new Error("Invalid local blob identity");
  if (completed.has(blob.sha)) return;
  const chunks = new Array(blob.chunks);
  for (let start = 0; start < blob.chunks; start += 4) {
    const indices = Array.from({length: Math.min(4, blob.chunks - start)}, (_, i) => start + i);
    const results = await Promise.allSettled(indices.map(i => tools.exec_command({
      cmd: `python scripts/publication_blob_chunk.py --sha ${blob.sha} --chunk-index ${i}`,
      workdir, max_output_tokens: 300000
    })));
    for (let j = 0; j < results.length; j++) {
      const result = results[j];
      if (result.status !== "fulfilled") throw result.reason;
      const index = indices[j], output = result.value.output;
      const rawSize = Math.min(blob.raw_chunk_bytes, blob.bytes - index * blob.raw_chunk_bytes);
      const expectedLength = 4 * Math.ceil(rawSize / 3);
      if (result.value.exit_code !== 0 || output.length !== expectedLength || !/^[A-Za-z0-9+/]*={0,2}$/.test(output)) {
        throw new Error(`Incomplete base64 for ${blob.sha} chunk ${index}`);
      }
      chunks[index] = output;
    }
  }
  const content = chunks.join("");
  if (content.length !== blob.base64_bytes) throw new Error("Assembled base64 length differs from immutable Git blob");
  const remote = payload(await tools.mcp__codex_apps__github_create_blob({
    repository_full_name: manifest.repository_full_name, encoding: "base64", content
  }));
  if (remote.sha !== blob.sha) throw new Error(`Remote blob SHA mismatch for ${blob.paths[0]}`);
  completed.add(blob.sha);store("hanjie_uploaded_blobs", [...completed]);
  count++;
  if (count % 15 === 0 || blob.bytes > 5000000 || count === manifest.uploads.length)
    notify({uploaded: count, total: manifest.uploads.length, bytes: blob.bytes, paths: blob.paths.length});
}
// Independent small immutable blobs can be uploaded concurrently. Large blobs
// remain sequential to keep base64 memory and connector payloads bounded.
for (let cursor = 0; cursor < manifest.uploads.length;) {
  const batch = [manifest.uploads[cursor++]];
  if (batch[0].bytes <= 5000000) {
    while (cursor < manifest.uploads.length && batch.length < 4 && manifest.uploads[cursor].bytes <= 5000000) {
      batch.push(manifest.uploads[cursor++]);
    }
  }
  const results = await Promise.allSettled(batch.map(uploadBlob));
  for (const result of results) if (result.status === "rejected") throw result.reason;
}
// Upload shallow directory objects bottom-up. Recursive path overlays can
// exceed GitHub's tree-build timeout on a large delivery directory.
const createdTrees = new Set(load("hanjie_uploaded_trees") || []);
const levels = [...new Set(manifest.shallow_tree_uploads.map(row => row.depth))].sort((a,b)=>b-a);
for (const depth of levels) {
  const rows = manifest.shallow_tree_uploads.filter(row => row.depth === depth && !createdTrees.has(row.sha));
  for (let index=0; index<rows.length; index+=4) {
    const results = await Promise.allSettled(rows.slice(index,index+4).map(async row => {
      const result = payload(await tools.mcp__codex_apps__github_create_tree({
        repository_full_name:manifest.repository_full_name, tree_elements:row.elements
      }));
      if (result.sha !== row.sha) throw new Error("Shallow directory SHA differs: " + row.paths.join(", "));
      createdTrees.add(row.sha);store("hanjie_uploaded_trees", [...createdTrees]);
    }));
    for (const result of results) if (result.status === "rejected") throw result.reason;
  }
}
if (!createdTrees.has(manifest.expected_tree_sha)) throw new Error("Reviewed root tree was not created");
const tree = {sha:manifest.expected_tree_sha};
store("hanjie_published_tree",tree.sha);
const commit = payload(await tools.mcp__codex_apps__github_create_commit({
  repository_full_name: manifest.repository_full_name, tree_sha: tree.sha,
  parent_sha: manifest.base_commit_sha, message: authorization.message
}));
store("hanjie_published_commit", commit.sha);
payload(await tools.mcp__codex_apps__github_update_ref({
  repository_full_name: manifest.repository_full_name, branch_name: manifest.branch_name,
  sha: commit.sha, force: false, expected_sha: manifest.base_commit_sha
}));
const verified = payload(await tools.mcp__codex_apps__github_fetch_commit({
  repo_full_name: manifest.repository_full_name, commit_sha: manifest.branch_name
})).commit.sha;
if (verified !== commit.sha) throw new Error("Final branch verification did not return the published commit");
text({branch: manifest.branch_name, commit: verified, tree: tree.sha, changed_paths: manifest.tree_elements.length,
      url: `https://github.com/${manifest.repository_full_name}/tree/${manifest.branch_name}`});
