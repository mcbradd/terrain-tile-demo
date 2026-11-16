# Open questions

Each row is an assumption made here, the question for the receiving team, and what changes if the answer differs.

| # | Assumption made here | Question | What changes if the answer differs |
| --- | --- | --- | --- |
| 1 | Positions only in terrain GLBs, shading from data textures, height packed in RG8 | Which vertex and texture formats does the engine take? | The exporters and the texture codec change. The rules do not. |
| 2 | Budgets are public anchors times a content share, in `profiles/` | What are the real budgets and device classes? | Edit one profile. Selection, batching, and rules follow. |
| 3 | Pixels per degree is 30 and 25, marked assumed | What display type and pixels per degree apply? | LOD selection error and entity LOD distances change. |
| 4 | NAVD88 orthometric heights, no conversion | Which vertical datum do consumers expect? | A geoid step is added to the build. |
| 5 | LOD is chosen statically per profile in the pipeline | Who owns runtime LOD policy? | The static selection becomes a default, or is dropped. |
| 6 | Public USGS elevation only | Which map data sources are allowed, and under what handling rules? | The fetch stage and the license files change. |
| 7 | Blender 5.2.0 is the authoring tool | Which DCC is of record? | The source gate is ported. The deliverable gate stays. |
| 8 | Source art is plain files in git | How is version control laid out, and what are the checkout rules? | Exclusive checkout and submit triggers are wired in. |
| 9 | `tilepipe validate` runs wherever a CI system calls it | Which CI system runs the build? | Only the job wrapper changes. The exit codes are the contract. |
| 10 | Entities are generic and unmarked | Which symbology standard applies, if any? | Entity content and naming change. |
| 11 | One tile of 4 by 4 chunks | How are multiple tiles streamed, and how are seams handled? | Chunking, skirts, and the manifest gain cross-tile rules. |
| 12 | Textures ship uncompressed and budgets count actual bytes | Which texture compression formats does the engine take? | Payload and texture sizes drop, and a codec stage is added. |
| 13 | The build uses the network for three listed commands only | Which tools and network access does the build environment permit? | Fetch moves to a pre-staged source, and install steps change. |
