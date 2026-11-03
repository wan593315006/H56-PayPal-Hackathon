# Vendored source identity

This package ships one frozen computation closure and does not edit it in place.
Every member below is pinned by byte, and `app.main selfcheck` re-verifies the whole
table on every run. There is no second source of truth: if a row does not match the
disk, the package is not the package that was assembled.

| field | value |
| --- | --- |
| schema | `H56_PACKAGE_VENDOR_RECORD_V1` |
| source_release_commit | `83484f79ad387296e623376f41b84bf1fb20d8ba` |
| upstream_core_commit | `9221e16460258bc81e1176d69f63a09f81159b73` |
| source_manifest_sha256 | `adeca462c152a7ee34c4bdee0f1f9b3833adab6b1aa5ae6e110d2ae58a42c6cb` |
| source_manifest_bytes | 42347 |
| members | 139 |
| member_bytes | 582506 |
| total_files_in_h56_core | 140 |
| extra_files_in_h56_core | 1 |
| extra_file | `offline_qualification_v1/SOURCE_MANIFEST.json` (42347 B, `adeca462c...c6cb`) |
| public_source_lock_sha256 | `060bbaa1976d243b9441a295c889fdf5dfa2252db66381ae669e6f5804ff07e3` |
| asset_manifest_sha256 | `a6c5461b9bf89f077d2e448c4019dec079555dd06dad0dabfed666efb428a825` |
| copied_at | 2026-11-03T02:14:23Z |
| copy_method | byte read/write, sha256 checked at source read and again at destination re-read |

## Members

| # | path | bytes | sha256 |
| ---: | --- | ---: | --- |
| 1 | `offline_qualification_v1/__init__.py` | 98 | `6ee5252b6fbfae56cdddd08de41c08f09ba18a291e2b576aea53bc1246ae9c14` |
| 2 | `offline_qualification_v1/assessment.py` | 4745 | `b133468c295f1053050023582b0fd046957131c3bb8c248d527d926a46d98259` |
| 3 | `offline_qualification_v1/assets.py` | 7853 | `5f9d9a1bb3bcec34554ce07d540952e1b1b2d364ffa9865159fa3e5764177a4d` |
| 4 | `offline_qualification_v1/assets/capability_catalog.json` | 2187 | `03d0dd4fa5e0aca893909f5bbfbdced08e299851504ac68a5ce01e20b59a311e` |
| 5 | `offline_qualification_v1/assets/environment_policy.json` | 2247 | `4608c0fbcf3617d3c5e059e4996bb36acb6e5d13ea6866e5a26c6bddcd97b5d7` |
| 6 | `offline_qualification_v1/assets/manifest.json` | 600 | `a6c5461b9bf89f077d2e448c4019dec079555dd06dad0dabfed666efb428a825` |
| 7 | `offline_qualification_v1/assets/state_mapping.json` | 2207 | `375957a1882842c99ef4a1cba0f0e4b18142045e86effddef142070b688b4de9` |
| 8 | `offline_qualification_v1/cli.py` | 5094 | `2ecd516d16b4e900880ebf25ce552de54df3b127377c9bf680d8bf87cc5ae3a8` |
| 9 | `offline_qualification_v1/contracts.py` | 9974 | `9043fc4ab6ded03f20eb11fef0154c152620fba774b412cad6525541daa4014d` |
| 10 | `offline_qualification_v1/core_bridge.py` | 18828 | `bdd054163e8fc24bbb9e75300d87300a96ad19f3ddd2c18346086c6ccb24c52f` |
| 11 | `offline_qualification_v1/evidence.py` | 4840 | `1d7f14b480ffe0d578c6a1ddd4454be7a0b8c5b1900f158ea798c2be0dc58bb8` |
| 12 | `offline_qualification_v1/fixtures/cases.json` | 16949 | `2a449b340a513aa371ab00da97094532f0aabf39188cc12d378aa2234df256f1` |
| 13 | `offline_qualification_v1/README.md` | 7385 | `659e91c730ea1d6887219c6d68460870c3ed17efdf2ad7d3aeb999818828cc4f` |
| 14 | `offline_qualification_v1/records.py` | 8548 | `1225fae7a5d14a4109a88882ebc25e62d04df7a9193735d3d85198c1e7d12c62` |
| 15 | `offline_qualification_v1/tests/test_boundary.py` | 12300 | `5e983cd5301d0260ef890be7818933b79c5c6a1dcec8a55052616a44a787767a` |
| 16 | `offline_qualification_v1/tests/test_core_chain.py` | 4864 | `3c9ead327fe22b80c35bd113ee7f1217b44d95335f57a353ffb4ab8c0f20277e` |
| 17 | `offline_qualification_v1/tests/test_evidence.py` | 5549 | `4146f0a64b47b01f7e2fe95011ac810b8c12273e1c048b31072149e92eebc122` |
| 18 | `offline_qualification_v1/tests/test_records.py` | 9142 | `e74107572bc096f779fcdefa03b4bb37b40b85b71b1ba1c0217eea5f7df7cafe` |
| 19 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_canonical_capability_contract_v0_1/.gitignore` | 73 | `882b1e62ba9093d6065e5fa32b50b728e10c4052bc20080a56be07b6c64669e1` |
| 20 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_canonical_capability_contract_v0_1/C1_C0_AUDIT_BINDING_V1.json` | 485 | `9dfad7c5fd22fa58379ceca71bd36b363a901842fa2cd05744f873e70ea7bf68` |
| 21 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_canonical_capability_contract_v0_1/CANDIDATE_CANONICAL_CAPABILITY_CONTRACT_V0_1_PROJECT_CARD.md` | 746 | `75f8d2ae79fd8852af6d21aa50821e78aef58228e56e1943d3794a188558c280` |
| 22 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_canonical_capability_contract_v0_1/CANDIDATE_CANONICAL_CAPABILITY_CONTRACT_V0_1_PROJECT_MANIFEST.json` | 3353 | `9ed5f996152a4de096206a54f09e9d6b8b2866a5ef2593cd1a9c619ea2e0c723` |
| 23 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_canonical_capability_contract_v0_1/CANDIDATE_CANONICAL_CAPABILITY_CONTRACT_V0_1_REQUIREMENT.md` | 2342 | `bfbd4a298bd0d7dcf3860b5255cb3935ef70cafcc9ae35f2e456082b1f8e53e9` |
| 24 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_canonical_capability_contract_v0_1/CANDIDATE_CANONICAL_CAPABILITY_CONTRACT_V0_1_STRUCTURED_SEMANTIC_REVIEW_INPUT_V1.json` | 2106 | `5baa4d0ce7876fa9affd50dadde230329790b1b61f1358b7cab76b82f98e20ba` |
| 25 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_canonical_capability_contract_v0_1/pyproject.toml` | 427 | `860e3f6b532a838a248bc42165c45278b0f1304bde7cb995ed01383c81cd9a8f` |
| 26 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_canonical_capability_contract_v0_1/README.md` | 1736 | `d3e6dd0e9740d50bb151596e0d90a339f3191bc7fe960d29f589c53aecbba78f` |
| 27 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_canonical_capability_contract_v0_1/src/candidate_canonical_capability_contract/__init__.py` | 335 | `1c04029b47e02f66c9b898d46dd2a063960b7ae48cb7ab5ff59c83cad5c9f315` |
| 28 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_canonical_capability_contract_v0_1/src/candidate_canonical_capability_contract/catalog.py` | 3899 | `3ad3fada5aabfd9c4a8281e335000396ee4c96db6b32da107e47f5481ae09d29` |
| 29 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_canonical_capability_contract_v0_1/src/candidate_canonical_capability_contract/contracts.py` | 7999 | `ce8ff9a3cb791fcd5a0ee480417f2730446cd2b28d6cf8fcf4d374efd16a98ac` |
| 30 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_canonical_capability_contract_v0_1/tests/test_candidate_canonical_capability_contract_v0_1.py` | 6221 | `065d109c8a424d936e5179a3bb587702f27ee1ba2ad51a20b1f8909e36d0a4a4` |
| 31 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_canonical_capability_contract_v0_1/tools/audit_candidate_canonical_capability_contract_v0_1_boundary.py` | 1882 | `d75b48dc0d0966b6f19b3f201dcf696621a7221ee6fc16b77653f7a8b85a3d77` |
| 32 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_canonical_capability_contract_v0_1/tools/build_candidate_canonical_capability_contract_v0_1_manifest.py` | 2503 | `026d4cd10e4ca3e2545e2c2e587e74623a31cef0b32ff35e1fad1748bc8c81ee` |
| 33 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_canonical_capability_contract_v0_1/tools/review_with_five_body.py` | 2450 | `2326448deea56dc93b4f7d4e91000e25fa8d6a4528ddd626e50e5c6a028c60fe` |
| 34 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_canonical_capability_contract_v0_1/tools/verify_c0_unified_capability_pool_audit_binding.py` | 2085 | `2013ec8146520aeed831dad73f3878afd81c2e1af147c7e18677c05d86c056d3` |
| 35 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_canonical_capability_contract_v0_1/tools/verify_candidate_canonical_capability_contract_v0_1_manifest.py` | 1015 | `e1aa58f215ddf41ab4e6417681dfcea26e8b432ccf0c82bc8a399a01efb7ea98` |
| 36 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_canonical_capability_contract_v0_1/tools/verify_candidate_canonical_capability_contract_v0_1_raw_git_identity.py` | 1481 | `7a1383109e5afcf35374c1f79bf91c6fd468251ab904f3fd47b4bee15a2faa6a` |
| 37 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_capability_feasibility_projection_v0_1/.gitignore` | 73 | `882b1e62ba9093d6065e5fa32b50b728e10c4052bc20080a56be07b6c64669e1` |
| 38 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_capability_feasibility_projection_v0_1/C2_C1_CONTRACT_BINDING_V1.json` | 496 | `5c78350d3890ec54d93af57127216ba17b5292ecf39160236854a794aa7a9f1c` |
| 39 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_capability_feasibility_projection_v0_1/CANDIDATE_CAPABILITY_FEASIBILITY_PROJECTION_V0_1_PROJECT_CARD.md` | 765 | `30dd96d3d2f31a0a41fb0f9804b00db623c3a906536e445c04c0b13bff668f2a` |
| 40 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_capability_feasibility_projection_v0_1/CANDIDATE_CAPABILITY_FEASIBILITY_PROJECTION_V0_1_PROJECT_MANIFEST.json` | 3327 | `15ffebac6cc9aeade60f629aef616213142f293863c246ad96c75fff649f939e` |
| 41 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_capability_feasibility_projection_v0_1/CANDIDATE_CAPABILITY_FEASIBILITY_PROJECTION_V0_1_REQUIREMENT.md` | 2304 | `f6fd9cb2de2db8c0a2502894a333b648983755259629bb34bcb38706e6d79f21` |
| 42 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_capability_feasibility_projection_v0_1/CANDIDATE_CAPABILITY_FEASIBILITY_PROJECTION_V0_1_STRUCTURED_SEMANTIC_REVIEW_INPUT_V1.json` | 2170 | `ec7b1da1f88624e49fe25562b114a6f590a99cacf2adb8a35dd6238a4ca4870f` |
| 43 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_capability_feasibility_projection_v0_1/pyproject.toml` | 424 | `0b6beb30b31f22cf6b319cdbb2c7e219d924e5049cdeefe3b43c6350d9ee9671` |
| 44 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_capability_feasibility_projection_v0_1/README.md` | 1647 | `b5bd2b2f0bde71b7015d899c206eae8e9b70f89990d7c86750283431eb181d69` |
| 45 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_capability_feasibility_projection_v0_1/src/candidate_capability_feasibility_projection/__init__.py` | 597 | `e9c7cf809f3233facd777757e538030664b3119aeb6dee7d46d46155c08c72b8` |
| 46 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_capability_feasibility_projection_v0_1/src/candidate_capability_feasibility_projection/contracts.py` | 15805 | `638d1644838758659613dc8073468686eb35fa7de75a50855164550faa60dd53` |
| 47 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_capability_feasibility_projection_v0_1/src/candidate_capability_feasibility_projection/evaluator.py` | 3398 | `b26b3cb09c1b54472cc86a22c9654c950ce3ed74647a8d591cf4e02934c8605b` |
| 48 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_capability_feasibility_projection_v0_1/tests/test_candidate_capability_feasibility_projection_v0_1.py` | 9412 | `9cfa9b9879681b4062bdfdd83297d444138fbaff218a245bdf84e60d69a06f16` |
| 49 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_capability_feasibility_projection_v0_1/tools/audit_candidate_capability_feasibility_projection_v0_1_boundary.py` | 1707 | `0946acb77fbeac90c3984c2e3fadd8249271aeaf7e4c78cc2607a5bcb89f92ef` |
| 50 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_capability_feasibility_projection_v0_1/tools/build_candidate_capability_feasibility_projection_v0_1_manifest.py` | 2526 | `2748df89ae5225c466bb2cd8367470db7c901ae799b37eda8545bab1e4d0b1c8` |
| 51 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_capability_feasibility_projection_v0_1/tools/review_with_five_body.py` | 2377 | `97276d2b7239229eeb57a011072002a6dd4ca44b265742c15a45ce5082a5148a` |
| 52 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_capability_feasibility_projection_v0_1/tools/verify_c1_canonical_capability_contract_binding.py` | 1944 | `b918358ac3464f7d58a8ee280fa87a027881dbbe1174675955a3f701821100e4` |
| 53 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_capability_feasibility_projection_v0_1/tools/verify_candidate_capability_feasibility_projection_v0_1_manifest.py` | 978 | `9921b1f5a19ddf0203a8327f70ed761d1085a7903b5ee079988ffcc6b7f1430a` |
| 54 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/candidate_capability_feasibility_projection_v0_1/tools/verify_candidate_capability_feasibility_projection_v0_1_raw_git_identity.py` | 1352 | `5ef4c169987e2e611dbe9daa5faa900752c6c97dd36bfa6eb4010541a9995b50` |
| 55 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k0_canonical_fact_foundation_v1/.gitignore` | 23 | `6feaded4e28ea86e001a6751b4e3d960e8b7c31b9616ff9936b79297086e809b` |
| 56 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k0_canonical_fact_foundation_v1/evidence/five_body_candidate_software_world_quality_review_py313.json` | 19105 | `505d54ec4d0925ff13977964b65a9581c71a9f44ae0d360421087e7aac9560bc` |
| 57 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k0_canonical_fact_foundation_v1/evidence/five_body_candidate_software_world_quality_review_py39.json` | 19105 | `505d54ec4d0925ff13977964b65a9581c71a9f44ae0d360421087e7aac9560bc` |
| 58 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k0_canonical_fact_foundation_v1/evidence/five_body_candidate_software_world_review.json` | 20014 | `dd02061f1e87376b60ff25fc98b3308c9e201e9a2bc4c6f3fa6422fcdec3fa25` |
| 59 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k0_canonical_fact_foundation_v1/evidence/k0_contract_validation_py313.json` | 1378 | `97a34b0a67d025087ca5bc9d80506d67de09f9e1d4a81cdca610a8a56bd3eb8a` |
| 60 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k0_canonical_fact_foundation_v1/evidence/k0_contract_validation_py39.json` | 1377 | `7e4529baec77df451e277a601bbcdf43d3193d7589d2b7ae129f1e3fdc62ee4a` |
| 61 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k0_canonical_fact_foundation_v1/K0_CANDIDATE_REVIEW_INPUT.md` | 850 | `b6a455317b958132de7c5333df3601814262043c595c21bacbbc09b1d6eea445` |
| 62 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k0_canonical_fact_foundation_v1/K0_FOUNDATION_CONTRACT.md` | 2821 | `7baa1dfb60674800f52352bdce59c6a0c7738f5e4c774b298272afaaf0af6bfd` |
| 63 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k0_canonical_fact_foundation_v1/K0_PROJECT_CARD.md` | 2315 | `50e7b1153f7d089f152f1961babbd939c6275c61799f556b1cce56ef0a011b7c` |
| 64 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k0_canonical_fact_foundation_v1/K0_PROJECT_MANIFEST.json` | 4879 | `676372048fc86f9041510c123c990e06f856b59c0361738fcc2491dba4875f43` |
| 65 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k0_canonical_fact_foundation_v1/K0_REQUIREMENT.md` | 1650 | `c7dc490fae0708a5b63f8299ea2b053c8015ecbbe5af16d6818bf29c86e0c75d` |
| 66 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k0_canonical_fact_foundation_v1/README.md` | 1862 | `a8855d75c4ade21bc144e2227447842eec08ca9274b14ee06a640be5a89c6cca` |
| 67 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k0_canonical_fact_foundation_v1/src/k0_fact_foundation/__init__.py` | 469 | `346c272bb4aadc4ebc96b673e7985a944973639db474a191d199caaf68672412` |
| 68 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k0_canonical_fact_foundation_v1/src/k0_fact_foundation/canonical.py` | 2191 | `ac22904b2ff296146671098db80bf5ab5e3ae555e62c48ff61ebf4c91da3b96f` |
| 69 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k0_canonical_fact_foundation_v1/src/k0_fact_foundation/contracts.py` | 7689 | `a895e765d4fcb96655f6e8e074c1c8b4e19c660ab5130401d295b784adf25841` |
| 70 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k0_canonical_fact_foundation_v1/src/k0_fact_foundation/history.py` | 3567 | `aade19b8d43dc2acb14dbe68e5f037b0532a7736f2f0afd5853488fe970545be` |
| 71 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k0_canonical_fact_foundation_v1/tests/test_canonical_fact_foundation.py` | 9228 | `d928dacda7d05841528a34bd9fbfd5f2767d3d27df949d097e2ff43160a6fa95` |
| 72 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k0_canonical_fact_foundation_v1/tools/review_with_five_body.py` | 3515 | `4a33abdf7b56a98547a76a3695e30ca2b6d09525f238fa4caef6e6456e8dd700` |
| 73 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k0_canonical_fact_foundation_v1/tools/verify_k0_contract.py` | 6357 | `dcc14e2b8dbdc3b715b867b119c5c6258d00d3e9c54305056e193f4d14260b85` |
| 74 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k1_state_derivation_foundation_v1/.gitignore` | 23 | `6feaded4e28ea86e001a6751b4e3d960e8b7c31b9616ff9936b79297086e809b` |
| 75 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k1_state_derivation_foundation_v1/evidence/five_body_candidate_software_world_quality_review_py313.json` | 19062 | `e52634153832c86854ed7fb5648746524ebf2f377fa206c566383bd1070dccf7` |
| 76 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k1_state_derivation_foundation_v1/evidence/five_body_candidate_software_world_quality_review_py39.json` | 19062 | `e52634153832c86854ed7fb5648746524ebf2f377fa206c566383bd1070dccf7` |
| 77 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k1_state_derivation_foundation_v1/evidence/five_body_candidate_software_world_review.json` | 18592 | `5147e008a4a8f19532201289ec7a3d132874b235fa272bcd68323fdb7ab88f68` |
| 78 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k1_state_derivation_foundation_v1/evidence/k1_contract_validation_py313.json` | 1774 | `4bdea9f431ce443a149447ea26d0e38bb24b426d7d0efd7416923e5bf5ba2bd1` |
| 79 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k1_state_derivation_foundation_v1/evidence/k1_contract_validation_py39.json` | 1773 | `e2c892d2903ea0619de279ebb13fe04521301c38cf2e2fb139a823a72994b207` |
| 80 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k1_state_derivation_foundation_v1/K1_CANDIDATE_REVIEW_INPUT.md` | 864 | `47c595745255267dc2fec0ee3cd6bfd3796ce82a4b9278ffe94d80e62389a043` |
| 81 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k1_state_derivation_foundation_v1/K1_PROJECT_CARD.md` | 2043 | `81a09fbf2e7beecefcea2b492ff01e17db9bf2a47f55320a8cdaf69648882e32` |
| 82 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k1_state_derivation_foundation_v1/K1_PROJECT_MANIFEST.json` | 4954 | `d4a2d92de08912c4fb5d7ba68af6b78e2ea3006e151f3b4dfac61e4c04d50ff7` |
| 83 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k1_state_derivation_foundation_v1/K1_REQUIREMENT.md` | 1303 | `8257fa0604f2815bc74b22ae36237c5b90af9e73240c24cf8b11fe2bf96f0934` |
| 84 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k1_state_derivation_foundation_v1/K1_STATE_DERIVATION_CONTRACT.md` | 1849 | `2e26dfb646f91d28cb708286b85ea496fea315e5cb04cc6926e953347b6fcfab` |
| 85 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k1_state_derivation_foundation_v1/README.md` | 1287 | `679ff9e18871e5b0110e43f623ac6f1ddeaff3d2151d4bf79f3bbca6561ca3c5` |
| 86 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k1_state_derivation_foundation_v1/src/k1_state_derivation/__init__.py` | 307 | `cf9c568ac2bee17fd4ffa738346bde0a803d9713e45a6de656642946370a6129` |
| 87 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k1_state_derivation_foundation_v1/src/k1_state_derivation/state_compiler.py` | 6324 | `b511aa6a41249a37e535edca0bad55349ac0ac62ebef282c54a6cc0091d32b09` |
| 88 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k1_state_derivation_foundation_v1/tests/test_state_derivation_foundation.py` | 8942 | `39f0098f85a1edc44377b61e5fc81c629698efd4dcfc6576a732e44509b1a415` |
| 89 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k1_state_derivation_foundation_v1/tools/review_with_five_body.py` | 3466 | `f14cb9ff7e53cb970b0f05591f0261fbcaa4132470fb5a2dad82247032159739` |
| 90 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/k1_state_derivation_foundation_v1/tools/verify_k1_contract.py` | 7878 | `8a6275ff7a988fb818ff56fa9980b293294f2ceeb480b147de9b95ec5c1c677d` |
| 91 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/unified_runtime_ontology_profile_v1_1/.gitignore` | 73 | `882b1e62ba9093d6065e5fa32b50b728e10c4052bc20080a56be07b6c64669e1` |
| 92 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/unified_runtime_ontology_profile_v1_1/pyproject.toml` | 510 | `6a281056bde9fafaf673a5621aca880dd3164ba2c63b7c5d4a61070fe2d0ed7a` |
| 93 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/unified_runtime_ontology_profile_v1_1/README.md` | 1996 | `cea6aeb48fdcba2e21938d816a75749b906968dec0ac90122aa3755ce8e526e0` |
| 94 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/unified_runtime_ontology_profile_v1_1/src/unified_runtime_ontology_profile/__init__.py` | 510 | `56f9003ef5c9c82bd6186da3249615654b47191c41010c1bf774b13dddbe06f3` |
| 95 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/unified_runtime_ontology_profile_v1_1/src/unified_runtime_ontology_profile/contracts.py` | 14276 | `a22b91374a8ac308f475f5b3eef45b038644337fc547452112251138b1d72ddd` |
| 96 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/unified_runtime_ontology_profile_v1_1/src/unified_runtime_ontology_profile/data/__init__.py` | 51 | `19cd2bca84eeb218aa44f930898b08e61756143d11c2f7a33a0dcae3f2f2b1a1` |
| 97 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/unified_runtime_ontology_profile_v1_1/src/unified_runtime_ontology_profile/data/UNIFIED_RUNTIME_ONTOLOGY_PROFILE_V1_1.json` | 4895 | `997ce3dcc07bde21365d35eb6d6a5c7d7454f6b4944d06f5a6e5aceedf399f6b` |
| 98 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/unified_runtime_ontology_profile_v1_1/src/unified_runtime_ontology_profile/profile.py` | 582 | `224a92da484933dd03a8085338036a9207782262127030f5299899c50c8170bf` |
| 99 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/unified_runtime_ontology_profile_v1_1/tests/test_unified_runtime_ontology_profile_v1_1.py` | 6667 | `25bb5f80d35f74512e6429f30b657bf67742b8920744089495b4bf7e99c1c14e` |
| 100 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/unified_runtime_ontology_profile_v1_1/tools/audit_unified_runtime_ontology_profile_v1_1_boundary.py` | 1106 | `87998a9482f795868d5f4adddc33637902e9f6e994f198fcb5f37d7cea849ed7` |
| 101 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/unified_runtime_ontology_profile_v1_1/tools/review_with_five_body.py` | 2208 | `ca4d589dade7f13d7d3b78aedf87997cd78da0013bffd5fa9df5e67bf7364198` |
| 102 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/unified_runtime_ontology_profile_v1_1/tools/verify_ontology_alignment_audit_binding.py` | 2063 | `10ca37df016f8b909bd93120c576ad6a5df2c4c1036f276133b9ceabcab718d9` |
| 103 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/unified_runtime_ontology_profile_v1_1/tools/verify_unified_runtime_ontology_profile_v1_1_manifest.py` | 1150 | `b4d8a3d5346b504ba24361debcf3d2ebab4a6439887116dcf3284ad3500d73fd` |
| 104 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/unified_runtime_ontology_profile_v1_1/tools/verify_unified_runtime_ontology_profile_v1_1_raw_git_identity.py` | 1581 | `7e15eb70a47919ed611d749e9fce78c2efa8244a6a4944b96eac58be32f602ca` |
| 105 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/unified_runtime_ontology_profile_v1_1/UNIFIED_RUNTIME_ONTOLOGY_PROFILE_V1_1_MANIFEST.json` | 3399 | `a99b493deac30ab134741b8d6a93137f21a543b7ee03c19ce1d8993af876e403` |
| 106 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/unified_runtime_ontology_profile_v1_1/UNIFIED_RUNTIME_ONTOLOGY_PROFILE_V1_1_REQUIREMENT.md` | 1331 | `36cc39ac98b1fed16602e65fd19ba8234b144b3de343eb75cad9d2ef799d9dbc` |
| 107 | `runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/unified_runtime_ontology_profile_v1_1/UNIFIED_RUNTIME_ONTOLOGY_PROFILE_V1_1_STRUCTURED_SEMANTIC_REVIEW_INPUT_V1.json` | 3001 | `21d0bc9b4d1606d783d50b0153dde32f7fbc4a60b296d13485a3b77eee8e4e6c` |
| 108 | `runtime_binding_v1_20261024/engineering/vendor/project_control_plane/AUDITS/UNIFIED_CAPABILITY_POOL_GAP_AUDIT_V1_20261004/AGENT_ORGANIZATION_PRECHECK.md` | 1308 | `71ab23a52ac712c2c9ce105137622e7ca9abf1d7ce2755ba72b69e369da7a54f` |
| 109 | `runtime_binding_v1_20261024/engineering/vendor/project_control_plane/AUDITS/UNIFIED_CAPABILITY_POOL_GAP_AUDIT_V1_20261004/AUDIT_MANIFEST.json` | 2126 | `f30f6e27191cc1af35d17fb9e27ce3d80c9315ab89b266afc6030d4039b87f65` |
| 110 | `runtime_binding_v1_20261024/engineering/vendor/project_control_plane/AUDITS/UNIFIED_CAPABILITY_POOL_GAP_AUDIT_V1_20261004/CAPABILITY_SURFACE_MANIFEST.json` | 3762 | `0f3e081263306227e372e6e7fd660a53ebb42b858db8e9b03b7a16d4455a5af0` |
| 111 | `runtime_binding_v1_20261024/engineering/vendor/project_control_plane/AUDITS/UNIFIED_CAPABILITY_POOL_GAP_AUDIT_V1_20261004/ENVIRONMENT/FINGERPRINT.json` | 262 | `36d034be45f8f447cfbfa0658ca28ad55b6a2522e37bd5c34cc2a6d1eca93f78` |
| 112 | `runtime_binding_v1_20261024/engineering/vendor/project_control_plane/AUDITS/UNIFIED_CAPABILITY_POOL_GAP_AUDIT_V1_20261004/EVIDENCE/SOURCE_MANIFEST.json` | 2047 | `b9d019924464f5b9f90ad09371f3be1ee94022287b6fbeed74c826f4613c59e8` |
| 113 | `runtime_binding_v1_20261024/engineering/vendor/project_control_plane/AUDITS/UNIFIED_CAPABILITY_POOL_GAP_AUDIT_V1_20261004/EVIDENCE/TEST_REPLAY_MANIFEST.json` | 607 | `050ba040e5e7c86039f231226e3b6fa838819bc83022e5abda0e82c5ecd012cf` |
| 114 | `runtime_binding_v1_20261024/engineering/vendor/project_control_plane/AUDITS/UNIFIED_CAPABILITY_POOL_GAP_AUDIT_V1_20261004/GAP_MATRIX.md` | 2753 | `2ed9a2697af699c5fddd05d60b526ee37e6fdc0ab8a61450ad93a9638676cb5c` |
| 115 | `runtime_binding_v1_20261024/engineering/vendor/project_control_plane/AUDITS/UNIFIED_CAPABILITY_POOL_GAP_AUDIT_V1_20261004/README.md` | 1924 | `eb1091b999280e6c2b3af2908b13904cfe022e7800d9e0378cf90e53db00dea0` |
| 116 | `runtime_binding_v1_20261024/engineering/vendor/project_control_plane/AUDITS/UNIFIED_CAPABILITY_POOL_GAP_AUDIT_V1_20261004/SPEC/UNIFIED_CAPABILITY_POOL_GAP_AUDIT_CONTRACT_V1.md` | 1774 | `d88383ba83b7f75f6114b941b90ff569ca0c2075348c4559959fcc38e47c1349` |
| 117 | `runtime_binding_v1_20261024/engineering/vendor/project_control_plane/AUDITS/UNIFIED_RUNTIME_ONTOLOGY_ALIGNMENT_AND_EVOLUTION_AUDIT_V1_20261004/AUDIT_MANIFEST.json` | 2639 | `485f260a4eb314e5470aad57806b5418a1e786b65f8825ccbf20b8125fa92bc4` |
| 118 | `runtime_binding_v1_20261024/engineering/vendor/project_control_plane/AUDITS/UNIFIED_RUNTIME_ONTOLOGY_ALIGNMENT_AND_EVOLUTION_AUDIT_V1_20261004/ENVIRONMENT/FINGERPRINT.json` | 415 | `cd065478477fd23bd753dcf28f538ce958f6a820a01ffdd5ccbb7f01629e6882` |
| 119 | `runtime_binding_v1_20261024/engineering/vendor/project_control_plane/AUDITS/UNIFIED_RUNTIME_ONTOLOGY_ALIGNMENT_AND_EVOLUTION_AUDIT_V1_20261004/EVIDENCE/CALL_CHAIN_MANIFEST.json` | 1504 | `7045081ad23d5cc259f00dfaf7b240967e6b21b989e6795dfb8076a378324f74` |
| 120 | `runtime_binding_v1_20261024/engineering/vendor/project_control_plane/AUDITS/UNIFIED_RUNTIME_ONTOLOGY_ALIGNMENT_AND_EVOLUTION_AUDIT_V1_20261004/EVIDENCE/SOURCE_MANIFEST.json` | 2738 | `ef78d0d7704d2f95d858fb01f27cdd4246ee9058282bd9faa6ebbc081177f63b` |
| 121 | `runtime_binding_v1_20261024/engineering/vendor/project_control_plane/AUDITS/UNIFIED_RUNTIME_ONTOLOGY_ALIGNMENT_AND_EVOLUTION_AUDIT_V1_20261004/EVIDENCE/TEST_REPLAY_MANIFEST.json` | 1472 | `4aaff2fce49970a9cc380bbb29565e913589434c85a1f997823fc03aadc402c6` |
| 122 | `runtime_binding_v1_20261024/engineering/vendor/project_control_plane/AUDITS/UNIFIED_RUNTIME_ONTOLOGY_ALIGNMENT_AND_EVOLUTION_AUDIT_V1_20261004/GAP_MATRIX.md` | 3898 | `320be6803a2b4915f858dc4ecb17cc71bf42905c98e7e1ea623a06e25136d948` |
| 123 | `runtime_binding_v1_20261024/engineering/vendor/project_control_plane/AUDITS/UNIFIED_RUNTIME_ONTOLOGY_ALIGNMENT_AND_EVOLUTION_AUDIT_V1_20261004/README.md` | 2263 | `2b8c234acc3e99a53d504c7a6ccbc2dec280e6f3e2be59ad3c7f39b2677fe3bf` |
| 124 | `runtime_binding_v1_20261024/engineering/vendor/project_control_plane/AUDITS/UNIFIED_RUNTIME_ONTOLOGY_ALIGNMENT_AND_EVOLUTION_AUDIT_V1_20261004/RECOMMENDATIONS/AUTHORITY_BOUNDARY.md` | 799 | `c740f54cb48290b6d9827072eef94340d011d52a8392a7642fef4f5f8907c507` |
| 125 | `runtime_binding_v1_20261024/engineering/vendor/project_control_plane/AUDITS/UNIFIED_RUNTIME_ONTOLOGY_ALIGNMENT_AND_EVOLUTION_AUDIT_V1_20261004/RECOMMENDATIONS/CORE_AND_EXTENSION_TERMS.json` | 1364 | `88bc2c84a845a03f8103a06cb258458d0341719349297be6b361f633333b0cef` |
| 126 | `runtime_binding_v1_20261024/engineering/vendor/project_control_plane/AUDITS/UNIFIED_RUNTIME_ONTOLOGY_ALIGNMENT_AND_EVOLUTION_AUDIT_V1_20261004/RECOMMENDATIONS/RELATION_VOCABULARY.md` | 2530 | `90c01f9f298e0cf91acf22875b668d55c75a053e0b3d6f0cc41eb12a15c790bd` |
| 127 | `runtime_binding_v1_20261024/engineering/vendor/project_control_plane/AUDITS/UNIFIED_RUNTIME_ONTOLOGY_ALIGNMENT_AND_EVOLUTION_AUDIT_V1_20261004/RECOMMENDATIONS/VERSION_AND_MIGRATION_RULES.md` | 1262 | `b136e5ed5dda9bd425af4abb446eee23904938fede59049f48f264525b3afad4` |
| 128 | `runtime_binding_v1_20261024/engineering/vendor/project_control_plane/AUDITS/UNIFIED_RUNTIME_ONTOLOGY_ALIGNMENT_AND_EVOLUTION_AUDIT_V1_20261004/SPEC/UNIFIED_RUNTIME_ONTOLOGY_ALIGNMENT_AND_EVOLUTION_AUDIT_CONTRACT_V1.md` | 2383 | `48d2e9f598a1596ee420a5e61e00781f134a7c196fd64bb0f34f73171ba75e85` |
| 129 | `runtime_windows/__init__.py` | 79 | `5ef0412a9c7915946e0775d58d37a6e1af5c61b029ece76acb87d22c19bd9b5b` |
| 130 | `runtime_windows/adapters/__init__.py` | 66 | `cbfa937e4d04d5e823b01350a35cfd6ef6ebe4c42c5e03630fb923e859283746` |
| 131 | `runtime_windows/adapters/bounded_rules.py` | 2463 | `dae3ace5ce2b1bce1049efd8fa91b6d2dc92e1c1464cde18b2a22dadb31ddbf1` |
| 132 | `runtime_windows/assembly/__init__.py` | 67 | `10e530dbc3a5d1256042d211702eb5b9bc865294677c4ca6ae51d14f7d1127e4` |
| 133 | `runtime_windows/assembly/contracts.py` | 5067 | `fa25ef91428db560914c8e3cfb7fbd81f72bb66f26646a3016c4d42df396913c` |
| 134 | `runtime_windows/errors.py` | 281 | `99ca4fd121e9528e897cbfc3d56adaad59e90fd2c7647403ee6bcffb58e70144` |
| 135 | `runtime_windows/paths.py` | 328 | `969473a1d679e50a80b5d2b33368ea8f369248f8e850cce53b44cd472a807389` |
| 136 | `runtime_windows/public-source-lock.json` | 25006 | `060bbaa1976d243b9441a295c889fdf5dfa2252db66381ae669e6f5804ff07e3` |
| 137 | `runtime_windows/runtime_admission.py` | 20631 | `94c0b3de37980374dc936feb1251576b5140d8d5e02748babb9143cc893ef4af` |
| 138 | `runtime_windows/source_identity.py` | 11985 | `36a3dce890ce107995870fad4d07d6a57d4b31ba921c211a2f7acbbd52637f7c` |
| 139 | `runtime_windows/task_store.py` | 7556 | `49aa85953a12c56d56cac243dd2fe942d374b55a7ba1eb05435a57a5ff166ebd` |

## Why the 140th file is not a member

`offline_qualification_v1/SOURCE_MANIFEST.json` is the declaration itself. A manifest
cannot contain its own sha256, so it is excluded from `runtime_required` by construction
and shipped as the one extra file. It is copied verbatim: re-serialising it would change
key order and whitespace, and `assets.source_manifest()` would reject the result before
any native byte is imported.

## Registered drive-letter literals (negative test payloads)

Three literal occurrences in two member files look like absolute Windows paths. They are
*inputs that must be rejected*, not references to any host directory, and they belong to
the boundary test suite. They are registered here by location so a scan can tell them
apart from an accidental leak. The literal text is deliberately not reproduced in this
document, so that this file introduces no new path-like string of its own.

| file | line | role |
| --- | ---: | --- |
| `offline_qualification_v1/fixtures/cases.json` | 487 | case field `malicious_path`: an out-of-tree path the request validator must refuse |
| `offline_qualification_v1/tests/test_boundary.py` | 141 | assertion input that must be refused |
| `offline_qualification_v1/tests/test_boundary.py` | 157 | assertion input that must be refused |

## Dependency posture

The frozen closure and the offline path import standard-library modules and vendored
bytes only: no third-party package is needed to run `selfcheck` or the offline
qualification chain. Real-mode components added in later stages live in `app/` and
declare their own pins in `requirements.txt`.

## How to verify

```
cd <package root>
python -B -m app.main selfcheck
```
