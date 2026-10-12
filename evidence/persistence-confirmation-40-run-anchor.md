# Cross-wave persistence 40-run evidence anchor

This commit timestamps the sealed evidence before any outcome analysis or transcript review.

- Public preregistration snapshot: `17aacb6dc6fb347c8e5c61ef642710be59e96f19`
- Frozen instrument commit: `8236caf2729de4f8f2b2c490ec9503e05a0d955e`
- Study: `persistence-confirmation`
- Signed study-manifest digest: `04158e8ae753d15a33eb01deeea363c866865cabf8166a9470b3882dd6d0e04a`
- Planned/recorded runs: `40/40`
- Total cost: `$1.562106600`

Pre-anchor verification: study signature valid; exact 40-run coverage and randomized order; every database hash and completion-manifest hash matches; all event chains, metadata, cost records, termination records, leakage scans, pre-run manifests, and Ed25519 signatures pass. The only expected outstanding verifier item is the public anchor receipt itself. The persistence contract gate also verified persistent-versus-erased reset semantics and causal cross-wave rescue scoring.

## Ordered run-manifest digests

1. `persist_blocked_permitted_ephemeral_GLM-5_3-Flash_rep12` — `b264b7d3b52b3bebe0c963b4c331134b7aedf5a23c3cad2812073f0fb2790fc3`
2. `persist_blocked_permitted_ephemeral_GLM-5_3-Flash_rep5` — `5226a6e6eb49afb08317e102de4135f6e1828ed459699b9caaa0ce12de5018c5`
3. `persist_blocked_permitted_persistent_GLM-5_3-Flash_rep5` — `c2be83dd0c44d95cd673a63659621089cf3036627ffda02482eaaec5d72cc906`
4. `persist_blocked_permitted_persistent_GLM-5_3-Flash_rep6` — `a23d06464b57772f24d1063e074fa2a939d36b5553b64c4b1bf664edc1d35af8`
5. `persist_blocked_permitted_persistent_GLM-5_3-Flash_rep14` — `a1c6b6883f0d23531682ae3f8b86f4475be2926f81ac2462693c631912849f4c`
6. `persist_blocked_permitted_persistent_GLM-5_3-Flash_rep7` — `a6e8bafebcb7227039850cfaa2d94e9dde0ae386936d1d3e722ec7275bec8209`
7. `persist_blocked_permitted_ephemeral_GLM-5_3-Flash_rep19` — `67c9721188cbaabae649475b84db9190f8d814d5acd9fd5e9221eeaa2ecb580a`
8. `persist_blocked_permitted_persistent_GLM-5_3-Flash_rep11` — `51c4bd2e46ab742f08f50b4ccbd64dc11d33728a44edfd65063d6bd94f8e7ace`
9. `persist_blocked_permitted_ephemeral_GLM-5_3-Flash_rep14` — `1e658187a9d3b4e7c002aa076456a9c114c83db6b45cfa7af25fa7b7be3520b6`
10. `persist_blocked_permitted_persistent_GLM-5_3-Flash_rep10` — `f8dfa0cc709942eff3f759c8ea7f9d0127227b1b51b2da3b376474c9be206a73`
11. `persist_blocked_permitted_ephemeral_GLM-5_3-Flash_rep3` — `4d844aaea9a65d0e19acd2f6db97188270f05564e92df0e3ab328cd3c6bdefc1`
12. `persist_blocked_permitted_ephemeral_GLM-5_3-Flash_rep7` — `386ab5b8b9e3049bf036a2a1eb7d80d95870ffbdc18e4c7cf33dbb2d7f05d624`
13. `persist_blocked_permitted_ephemeral_GLM-5_3-Flash_rep17` — `5ffad20e38bc9d8876bc36de0e2e9dab8fe92af7ec3493efb3109dc9edd781df`
14. `persist_blocked_permitted_persistent_GLM-5_3-Flash_rep18` — `2e4a691865b2dd32080e79c38fc3c60a167b2129a7488d9a4c4c48a1fe37516e`
15. `persist_blocked_permitted_persistent_GLM-5_3-Flash_rep8` — `74cdd145be52b696c4c8ad9c267ad4ab8c67b74504b011dc372f3d17ae8771d1`
16. `persist_blocked_permitted_ephemeral_GLM-5_3-Flash_rep4` — `012fbd183a58248c6a6d03c7734fe80a1ab9194ea107e2d8896e025cc543c12d`
17. `persist_blocked_permitted_ephemeral_GLM-5_3-Flash_rep18` — `7d4df74fa61451bbef398659003fd4374ed02db13787801bb4e90a61ceeba8c7`
18. `persist_blocked_permitted_persistent_GLM-5_3-Flash_rep15` — `7a42089157d31ac1f87db18665755fbe9cd6895c6c7671eda26a3c2907be6d0b`
19. `persist_blocked_permitted_ephemeral_GLM-5_3-Flash_rep8` — `d5deca35af5c9a5de1aaaa8e880a10613cbb1a08e5cf5c91e50a08d477b5d081`
20. `persist_blocked_permitted_persistent_GLM-5_3-Flash_rep3` — `730cbb01460325c03c5e9dfddb2673e83b989eabd8d8e7fd4df170116fd679e5`
21. `persist_blocked_permitted_persistent_GLM-5_3-Flash_rep9` — `7e01fc7af13201e888a7f8ff64e152ab6520117c51d953081cf8c52f9ac73847`
22. `persist_blocked_permitted_ephemeral_GLM-5_3-Flash_rep10` — `8ff500a8aaf04f303c4979383ef22eaa62c626847f792e1bb825e5689ea09b7a`
23. `persist_blocked_permitted_ephemeral_GLM-5_3-Flash_rep13` — `fa161d7835cb498ae1ea20b1acf907394380cc2f6f0cc62f192e652f8b220583`
24. `persist_blocked_permitted_persistent_GLM-5_3-Flash_rep4` — `dbc7ee4f94080b5b05e06e44c18f494a75d988ddca0fc75cd1d5b496a0b14824`
25. `persist_blocked_permitted_ephemeral_GLM-5_3-Flash_rep6` — `01141952acb1d1c72cb27a9b301662b9182a1ee8b3e1597c679e35773ded84ef`
26. `persist_blocked_permitted_persistent_GLM-5_3-Flash_rep19` — `7792fa659db80c6046638d705c7ab999ff9571e5de1321ebe6559be37d0cd534`
27. `persist_blocked_permitted_persistent_GLM-5_3-Flash_rep13` — `337f7703efb1bc464a5728c0fb3991c923e99849e9b3c99a09651aebadf45c0b`
28. `persist_blocked_permitted_ephemeral_GLM-5_3-Flash_rep15` — `c053718842ac67ae4e19c52036e593b33761035862383217743f7013fd8b3a25`
29. `persist_blocked_permitted_persistent_GLM-5_3-Flash_rep1` — `bedcdef24a1b587d6b2719f19f1ab9c017395855ced4fd644408339d412134f4`
30. `persist_blocked_permitted_persistent_GLM-5_3-Flash_rep17` — `5e58d60ea5d4a803175d765dcd63f18713d554a31f50e1dde2f09e9370407226`
31. `persist_blocked_permitted_ephemeral_GLM-5_3-Flash_rep1` — `bd186fada1e98cd2bc530721d397c7e3ace8253b644d7c21956e7cdd179df677`
32. `persist_blocked_permitted_persistent_GLM-5_3-Flash_rep16` — `8544e6a81b0ce6ca898fe64a5da14f84dfd3587cc43d57918bc280af37e44d4d`
33. `persist_blocked_permitted_persistent_GLM-5_3-Flash_rep20` — `f9f2a97606302da6f9f5bbaa3490de10d0b561c6301d49fc92922848b5c81877`
34. `persist_blocked_permitted_persistent_GLM-5_3-Flash_rep2` — `65a96ed1998d770721aa918d26b08fb93e24156f66c5ef15aa534c87e4bc52b4`
35. `persist_blocked_permitted_ephemeral_GLM-5_3-Flash_rep2` — `0921b120f2a4ea3051f6653e4c58233001349d80002a574b74caf15f9ac05a63`
36. `persist_blocked_permitted_ephemeral_GLM-5_3-Flash_rep9` — `08f508261d87558728a0f8e6fd39b50fbd9d5cb4bfa1c83f4d0fd8cd2baa9bc5`
37. `persist_blocked_permitted_ephemeral_GLM-5_3-Flash_rep11` — `6469002089b918434f31427cc61e82d2030f12a0e530ab48c68056297631445b`
38. `persist_blocked_permitted_ephemeral_GLM-5_3-Flash_rep20` — `bbaef3d1ed5aab11b5a178d9f859f4900cf6efde2a51029f5297186f9c9ace8b`
39. `persist_blocked_permitted_persistent_GLM-5_3-Flash_rep12` — `d6df052737069d6ed090fdd823617e8dd3db0be855fc63b61430cdcc2d2c9c58`
40. `persist_blocked_permitted_ephemeral_GLM-5_3-Flash_rep16` — `515ad967456d91ea74e94544a13a9274653093fe14a77517bf6b5c95a7cdd8ee`
