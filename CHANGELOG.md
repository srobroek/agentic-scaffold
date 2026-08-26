# Changelog

## [3.0.4](https://github.com/srobroek/agentic-scaffold/compare/v3.0.3...v3.0.4) (2026-08-26)


### Bug Fixes

* **cli:** skip disabled questions in the validator preflight, pin the real recipe ([2f6a6b1](https://github.com/srobroek/agentic-scaffold/commit/2f6a6b1b1120fe4aec8e8a448498cb12eeccad32))

## [3.0.3](https://github.com/srobroek/agentic-scaffold/compare/v3.0.2...v3.0.3) (2026-08-26)


### Bug Fixes

* **cli:** run question validators in the check-answers preflight ([bec5363](https://github.com/srobroek/agentic-scaffold/commit/bec536346a9ebb4e40a670e662a34316517f11c6))

## [3.0.2](https://github.com/srobroek/agentic-scaffold/compare/v3.0.1...v3.0.2) (2026-08-26)


### Bug Fixes

* **recipes:** refuse api-refs languages that have no extractor ([0ac4aaa](https://github.com/srobroek/agentic-scaffold/commit/0ac4aaa3eef1758baa612c57e650002090e8ee4d))

## [3.0.1](https://github.com/srobroek/agentic-scaffold/compare/v3.0.0...v3.0.1) (2026-08-26)


### Bug Fixes

* **skills:** the run-record section follows the render it depends on ([180e2a7](https://github.com/srobroek/agentic-scaffold/commit/180e2a7ba212a3578e432da8f707f0cd06cc9d10))

## [3.0.0](https://github.com/srobroek/agentic-scaffold/compare/v2.0.0...v3.0.0) (2026-08-26)


### ⚠ BREAKING CHANGES

* **cli:** --profile no longer ignores positional recipes.

### Features

* **cli:** union --profile with positional recipes ([#15](https://github.com/srobroek/agentic-scaffold/issues/15)) ([d880a5b](https://github.com/srobroek/agentic-scaffold/commit/d880a5baf09dce7b0e4ad623e432b40690a62bec))

## [2.0.0](https://github.com/srobroek/agentic-scaffold/compare/v1.1.0...v2.0.0) (2026-08-26)


### ⚠ BREAKING CHANGES

* rules/choices.md no longer derives a licence.

### Bug Fixes

* resolve the checkout, reconfirm remembered answers, unrule the licence ([#14](https://github.com/srobroek/agentic-scaffold/issues/14)) ([1e1b1cd](https://github.com/srobroek/agentic-scaffold/commit/1e1b1cdac4d85c00fa79430c31f0aabd5bbb94de))


### Refactors

* one version source, two catalogs ([#12](https://github.com/srobroek/agentic-scaffold/issues/12)) ([9f89d08](https://github.com/srobroek/agentic-scaffold/commit/9f89d088e8fb33ad762837ba4fceba08c921f7b5))

## [1.1.0](https://github.com/srobroek/agentic-scaffold/compare/v1.0.0...v1.1.0) (2026-08-26)


### Features

* serve the skills from a marketplace catalog again ([#9](https://github.com/srobroek/agentic-scaffold/issues/9)) ([bf14428](https://github.com/srobroek/agentic-scaffold/commit/bf144289bf14e7a18e9e227f66473ddb5d881550))


### Bug Fixes

* point the catalog source at "./", which the normalizer keeps ([#11](https://github.com/srobroek/agentic-scaffold/issues/11)) ([fd69dbd](https://github.com/srobroek/agentic-scaffold/commit/fd69dbd8c179e7fab6cd5b427321327db86139a6))

## [1.0.0](https://github.com/srobroek/agentic-scaffold/compare/v0.2.2...v1.0.0) (2026-08-26)


### ⚠ BREAKING CHANGES

* dep-updates defaults auto_merge to false, and release_type defaults to detection.
* `workspace/moon` does not ask `project_name` or `node_version`, and `layout` defaults to empty.
* `templates/` is now `recipes/`.

### Features

* add just setup, one repomix artefact, the rtk layer, and beads recipes ([6d31347](https://github.com/srobroek/agentic-scaffold/commit/6d31347a6b16c0be6d58223876792263226cf8b9))
* add opengrep scanning with layer-derived rulesets ([1ca739b](https://github.com/srobroek/agentic-scaffold/commit/1ca739b9c4b30a1fb0cab90ce27dfd831aa4044b))
* add the iac/cdk and workspace/devcontainer layers ([646a4a1](https://github.com/srobroek/agentic-scaffold/commit/646a4a19c2e4febb87038e8f08ae83308cddd53e))
* add the lang/api and agentic/marketplace layers ([6a0b587](https://github.com/srobroek/agentic-scaffold/commit/6a0b5871cf3144f4a2835afbd109aae9037860df))
* add the profiles, their validator, and the render-every-profile check ([cadb825](https://github.com/srobroek/agentic-scaffold/commit/cadb8252a19bc4d75dd9fd1474ed781fa1cc7d10))
* add the skill, publish this repo as its own package, enforce commits in CI ([257f8b8](https://github.com/srobroek/agentic-scaffold/commit/257f8b85cad4b15cc917f3715ec0a37207ff9e7e))
* **agentic/index:** report pack staleness instead of packing at session start ([6c5d0fb](https://github.com/srobroek/agentic-scaffold/commit/6c5d0fb47a6d48c9866e5a21b675532e57627d2b))
* **agentic/package:** add the self-publishing marketplace layer ([5eec3ad](https://github.com/srobroek/agentic-scaffold/commit/5eec3ad76c8aea56c7938f7049b922291a30dcaa))
* **agentic/speckit:** add the SpecKit layer over speckit-conductor ([9319848](https://github.com/srobroek/agentic-scaffold/commit/9319848732169060ef37cad04de3f024aa09a3de))
* **agentic:** port the apm and beads layers, and fix AGENTS.md ownership ([08909ce](https://github.com/srobroek/agentic-scaffold/commit/08909cebe45f9dad9b1cef2a865bdf167f7717b6))
* **beads:** set the surveyed config properties and push the database at pre-push ([cdc549d](https://github.com/srobroek/agentic-scaffold/commit/cdc549d149090b44dbdcd5247ac45edefdc81e2c))
* **container/image:** add the container layer ([942b863](https://github.com/srobroek/agentic-scaffold/commit/942b863df671e53c9e097b1bd0f91924b5c42484))
* **docs-api-refs:** add the API reference layer ([5ea5d82](https://github.com/srobroek/agentic-scaffold/commit/5ea5d82ccbc3f2f06660c9957c7d30d7a0328356))
* **docs/agents:** generate the steering from what is on disk ([eafe0d1](https://github.com/srobroek/agentic-scaffold/commit/eafe0d1024946d5864e1454e773444771c69329f))
* **docs:** add the adr and site layers, and pin the setup recipes against drift ([f36d5e8](https://github.com/srobroek/agentic-scaffold/commit/f36d5e857891391a156d1459935b0a3b975171c6))
* **docs:** add the two deploy topologies ([8f2066c](https://github.com/srobroek/agentic-scaffold/commit/8f2066c6fa21d68a9f974ff22dc25275f3a42b73))
* enforce generator-output evidence, and add the pack-code recipe ([d8ce6d1](https://github.com/srobroek/agentic-scaffold/commit/d8ce6d1d512099b3f292bc89db2e9eb3a188afa8))
* generate the GitHub CI caller, and settle moon from the workspace manifest ([b825f15](https://github.com/srobroek/agentic-scaffold/commit/b825f15f01b462ad0f2268a8c0b28357d6441d27))
* **host/github:** port the language-blind CI and governance layer ([622fa73](https://github.com/srobroek/agentic-scaffold/commit/622fa7348f44b6fdefa08a5efb5d37c30f05dc79))
* **host/github:** settle repository governance and apply it ([aed5a4d](https://github.com/srobroek/agentic-scaffold/commit/aed5a4d8d0f3fb65b8f63fd807e0067cae35c214))
* **host/gitlab:** add the GitLab pipeline and governance layer ([4bc8339](https://github.com/srobroek/agentic-scaffold/commit/4bc833920fea6d8a12c3a283f67eaaa5abc54303))
* **iac/terraform:** add the OpenTofu layer ([783203a](https://github.com/srobroek/agentic-scaffold/commit/783203a15a1c0d1b3fca8e87059a4d12c05bdc7a))
* **quality/hooks:** move the three git-action agent hooks into prek ([8b2c8be](https://github.com/srobroek/agentic-scaffold/commit/8b2c8bea95f9f191bc98b41ad4c6cbcf4af42960))
* **quality/hooks:** port the hook layer and enforce the set in CI ([8c9e42f](https://github.com/srobroek/agentic-scaffold/commit/8c9e42f9ead01ad100e13e20fece9fdd1c81a2a0))
* **quality/hooks:** render ADR files from beads decision beads ([16bd0f1](https://github.com/srobroek/agentic-scaffold/commit/16bd0f11ff02dc0df08ef7053e5da77828591c6d))
* rebuild around recipes/, one scaffold CLI, and a beads run record ([86fae82](https://github.com/srobroek/agentic-scaffold/commit/86fae82a3a79fc068e895c496f455760af25a068))
* **release,container:** publish SBOMs and attest build provenance ([16b8372](https://github.com/srobroek/agentic-scaffold/commit/16b837213b29fd9b8ce84fd78009a2842f4db8f8))
* **release/goreleaser:** publish binaries on the tag release-please pushes ([5137e14](https://github.com/srobroek/agentic-scaffold/commit/5137e1488da43aa1271d1aa34c86f84d65ad8094))
* **release:** mint an App token so the release PR triggers CI ([44873ae](https://github.com/srobroek/agentic-scaffold/commit/44873aee1f8c3fae6a801a8f369f7cb9e9a31c08))
* **release:** port release-please and dep-updates, add cocogitto ([cc979b6](https://github.com/srobroek/agentic-scaffold/commit/cc979b676de9aaeb7cc48fa6303fd052ee16bf54))
* **release:** sync the marketplace catalogs onto the release branch ([437f4df](https://github.com/srobroek/agentic-scaffold/commit/437f4dfb3348689cc65ac966cc53d72ec0347234))
* split setup and setup-worktree, and copy the dependency trees ([04608ed](https://github.com/srobroek/agentic-scaffold/commit/04608edc7fcdbb28d0d292c9aab43f27a8f6df0c))
* **update-skill:** add project-scaffold-update ([1177f75](https://github.com/srobroek/agentic-scaffold/commit/1177f758f15665a7dcc81c654cceccfffccbffb8))
* user-named marketplaces, native publisher, and derived answers ([#8](https://github.com/srobroek/agentic-scaffold/issues/8)) ([8e00329](https://github.com/srobroek/agentic-scaffold/commit/8e00329ce12ebd25cbaf5c2c9ec4e4f5f37cf822))
* **workspace/just:** port the task-surface layer ([df04169](https://github.com/srobroek/agentic-scaffold/commit/df04169b319131b4a477a75f4a20f7d516054170))
* **workspace/monorepo:** add the workspace layer and just add ([b874718](https://github.com/srobroek/agentic-scaffold/commit/b87471844b38d82f63e1604eda3e14db36b5ed06))
* **workspace/moon:** add the member graph layer ([a5d7b07](https://github.com/srobroek/agentic-scaffold/commit/a5d7b07565570fabfd360d3d4523dab8f1ef3cfa))


### Bug Fixes

* **adr:** open records with frontmatter and keep the index current ([1a382d6](https://github.com/srobroek/agentic-scaffold/commit/1a382d65cc6d8668437d1feee897d639a34724ab))
* **apm:** restore the kiro rationale release-please stripped ([67f6079](https://github.com/srobroek/agentic-scaffold/commit/67f607945a1fe0a98bd892369b0821e947d9690f))
* **base/gitignore:** take the OS artifacts from gitnr on every render ([a0e1e58](https://github.com/srobroek/agentic-scaffold/commit/a0e1e58f7477a759f990f3d2671388ffb95e5382))
* **cdk:** unset CI for the projen synth, and add a test-ci recipe ([bd738ab](https://github.com/srobroek/agentic-scaffold/commit/bd738ab15663556b37082c1f346cc14157cf526c))
* **ci:** pin apm, let Actions open the release PR, and bound release history ([d51ef3e](https://github.com/srobroek/agentic-scaffold/commit/d51ef3ea306ee33d77eb8e97225bca2a01c6cbfd))
* **ci:** pin the runtimes layers need, and stop two tests depending on this machine ([6f3d85b](https://github.com/srobroek/agentic-scaffold/commit/6f3d85b34169daf4484ada39668b7a25b5518a93))
* **ci:** pin yamllint to a version that exists ([803a52c](https://github.com/srobroek/agentic-scaffold/commit/803a52c56599f059e8c726247f48025210ccacb2))
* exclude filesystem artifacts from every rendered layer ([c8d8a98](https://github.com/srobroek/agentic-scaffold/commit/c8d8a982d8801cd15549a87337ff94ae4fd8dd82))
* **iac/cdk:** keep rationale out of a recipe description ([4001346](https://github.com/srobroek/agentic-scaffold/commit/40013461cb38849d2a76ff32678bb0248e9235b9))
* **index:** derive docs/INDEX.md from tracked files, not the filesystem ([688e64b](https://github.com/srobroek/agentic-scaffold/commit/688e64bb0bbe1d56e31a996f60d0aa1ae2d482e5))
* **lang/api:** state its security posture rather than omitting the fragment ([512b275](https://github.com/srobroek/agentic-scaffold/commit/512b275bfb240c0b6603a7204bf0bde2584a05f5))
* lint this repository's own config, and correct three lying action pins ([8911188](https://github.com/srobroek/agentic-scaffold/commit/8911188cac2cbc00fc8fe116e1bf9508fb1487c2))
* **lint:** drop the checkout fallback from the prose gate ([d66cf0c](https://github.com/srobroek/agentic-scaffold/commit/d66cf0ca32455bcb77717bac251d1b8a83582433))
* move the prose gate to slopvac, and widen the gitnr retry ([7db7c61](https://github.com/srobroek/agentic-scaffold/commit/7db7c61fabe4042ca5de75277a982ca7cb82674e))
* **release:** add package-build, and check for it before syncing ([ca2793e](https://github.com/srobroek/agentic-scaffold/commit/ca2793efcc14bc315cf78df510ff88af860cd850))
* **release:** degrade when the app credentials are absent ([9566eea](https://github.com/srobroek/agentic-scaffold/commit/9566eeadc61ed78092d5525edb9a2b2aab6ffab9))
* **release:** give the repository a release workflow and gate the catalogs ([cb711af](https://github.com/srobroek/agentic-scaffold/commit/cb711affe6eb33a6d7731237572df589a359cc1d))
* **release:** repair apm.yml after a release instead of blocking on it ([ecc599a](https://github.com/srobroek/agentic-scaffold/commit/ecc599acb8e784a6b7d53d1c5ec125f3349ca745))
* **release:** require the app credentials, with no GITHUB_TOKEN fallback ([e4dab30](https://github.com/srobroek/agentic-scaffold/commit/e4dab308d413ef683a353280acb0265735814cd0))
* **release:** scope the App token, and use the real private key ([6a18ff4](https://github.com/srobroek/agentic-scaffold/commit/6a18ff447b3cc09f9cb1fe3b258d7e44ac19ea10))
* **tests:** resolve pinned tools through mise, not an installs/latest path ([0d29846](https://github.com/srobroek/agentic-scaffold/commit/0d298463815c2410cf152bf27808188230a55883))


### Refactors

* **release:** register members in just add, not a sync script ([248cc37](https://github.com/srobroek/agentic-scaffold/commit/248cc37a667a7f357430bc29689e59b17926e108))


### Documentation

* clear the 64 prose-gate errors from the updated vale ruleset ([c697581](https://github.com/srobroek/agentic-scaffold/commit/c69758116dfa44b2b5aa6b5ca2c8c0b206cda1aa))
* drop the gotchas trees ([9bb58f0](https://github.com/srobroek/agentic-scaffold/commit/9bb58f0802886aa66094ef76120cff1044f6549e))
* **gitlab:** record that the layer ships no governance script ([932a0ed](https://github.com/srobroek/agentic-scaffold/commit/932a0edfffa34fa71458c7e0c6d4bebf35e615de))
* settle the better-t-stack option defaults ([5b21385](https://github.com/srobroek/agentic-scaffold/commit/5b21385b70f7d6f1534db12585267771a420c729))

## [0.2.2](https://github.com/srobroek/agentic-scaffold/compare/srobroek-project-scaffold--v0.2.1...srobroek-project-scaffold--v0.2.2) (2026-08-17)


### Documentation

* **gitlab:** record that the layer ships no governance script ([932a0ed](https://github.com/srobroek/agentic-scaffold/commit/932a0edfffa34fa71458c7e0c6d4bebf35e615de))

## [0.2.1](https://github.com/srobroek/agentic-scaffold/compare/srobroek-project-scaffold--v0.2.0...srobroek-project-scaffold--v0.2.1) (2026-08-17)


### Bug Fixes

* **apm:** restore the kiro rationale release-please stripped ([67f6079](https://github.com/srobroek/agentic-scaffold/commit/67f607945a1fe0a98bd892369b0821e947d9690f))
* **release:** repair apm.yml after a release instead of blocking on it ([ecc599a](https://github.com/srobroek/agentic-scaffold/commit/ecc599acb8e784a6b7d53d1c5ec125f3349ca745))

## [0.2.0](https://github.com/srobroek/agentic-scaffold/compare/srobroek-project-scaffold--v0.1.0...srobroek-project-scaffold--v0.2.0) (2026-08-17)


### Features

* add just setup, one repomix artefact, the rtk layer, and beads recipes ([6d31347](https://github.com/srobroek/agentic-scaffold/commit/6d31347a6b16c0be6d58223876792263226cf8b9))
* add opengrep scanning with layer-derived rulesets ([1ca739b](https://github.com/srobroek/agentic-scaffold/commit/1ca739b9c4b30a1fb0cab90ce27dfd831aa4044b))
* add the iac/cdk and workspace/devcontainer layers ([646a4a1](https://github.com/srobroek/agentic-scaffold/commit/646a4a19c2e4febb87038e8f08ae83308cddd53e))
* add the lang/api and agentic/marketplace layers ([6a0b587](https://github.com/srobroek/agentic-scaffold/commit/6a0b5871cf3144f4a2835afbd109aae9037860df))
* add the profiles, their validator, and the render-every-profile check ([cadb825](https://github.com/srobroek/agentic-scaffold/commit/cadb8252a19bc4d75dd9fd1474ed781fa1cc7d10))
* add the skill, publish this repo as its own package, enforce commits in CI ([257f8b8](https://github.com/srobroek/agentic-scaffold/commit/257f8b85cad4b15cc917f3715ec0a37207ff9e7e))
* **agentic/index:** report pack staleness instead of packing at session start ([6c5d0fb](https://github.com/srobroek/agentic-scaffold/commit/6c5d0fb47a6d48c9866e5a21b675532e57627d2b))
* **agentic/package:** add the self-publishing marketplace layer ([5eec3ad](https://github.com/srobroek/agentic-scaffold/commit/5eec3ad76c8aea56c7938f7049b922291a30dcaa))
* **agentic/speckit:** add the SpecKit layer over speckit-conductor ([9319848](https://github.com/srobroek/agentic-scaffold/commit/9319848732169060ef37cad04de3f024aa09a3de))
* **agentic:** port the apm and beads layers, and fix AGENTS.md ownership ([08909ce](https://github.com/srobroek/agentic-scaffold/commit/08909cebe45f9dad9b1cef2a865bdf167f7717b6))
* **beads:** set the surveyed config properties and push the database at pre-push ([cdc549d](https://github.com/srobroek/agentic-scaffold/commit/cdc549d149090b44dbdcd5247ac45edefdc81e2c))
* **container/image:** add the container layer ([942b863](https://github.com/srobroek/agentic-scaffold/commit/942b863df671e53c9e097b1bd0f91924b5c42484))
* **docs-api-refs:** add the API reference layer ([5ea5d82](https://github.com/srobroek/agentic-scaffold/commit/5ea5d82ccbc3f2f06660c9957c7d30d7a0328356))
* **docs/agents:** generate the steering from what is on disk ([eafe0d1](https://github.com/srobroek/agentic-scaffold/commit/eafe0d1024946d5864e1454e773444771c69329f))
* **docs:** add the adr and site layers, and pin the setup recipes against drift ([f36d5e8](https://github.com/srobroek/agentic-scaffold/commit/f36d5e857891391a156d1459935b0a3b975171c6))
* **docs:** add the two deploy topologies ([8f2066c](https://github.com/srobroek/agentic-scaffold/commit/8f2066c6fa21d68a9f974ff22dc25275f3a42b73))
* enforce generator-output evidence, and add the pack-code recipe ([d8ce6d1](https://github.com/srobroek/agentic-scaffold/commit/d8ce6d1d512099b3f292bc89db2e9eb3a188afa8))
* **host/github:** port the language-blind CI and governance layer ([622fa73](https://github.com/srobroek/agentic-scaffold/commit/622fa7348f44b6fdefa08a5efb5d37c30f05dc79))
* **host/github:** settle repository governance and apply it ([aed5a4d](https://github.com/srobroek/agentic-scaffold/commit/aed5a4d8d0f3fb65b8f63fd807e0067cae35c214))
* **host/gitlab:** add the GitLab pipeline and governance layer ([4bc8339](https://github.com/srobroek/agentic-scaffold/commit/4bc833920fea6d8a12c3a283f67eaaa5abc54303))
* **iac/terraform:** add the OpenTofu layer ([783203a](https://github.com/srobroek/agentic-scaffold/commit/783203a15a1c0d1b3fca8e87059a4d12c05bdc7a))
* **quality/hooks:** move the three git-action agent hooks into prek ([8b2c8be](https://github.com/srobroek/agentic-scaffold/commit/8b2c8bea95f9f191bc98b41ad4c6cbcf4af42960))
* **quality/hooks:** port the hook layer and enforce the set in CI ([8c9e42f](https://github.com/srobroek/agentic-scaffold/commit/8c9e42f9ead01ad100e13e20fece9fdd1c81a2a0))
* **quality/hooks:** render ADR files from beads decision beads ([16bd0f1](https://github.com/srobroek/agentic-scaffold/commit/16bd0f11ff02dc0df08ef7053e5da77828591c6d))
* **release,container:** publish SBOMs and attest build provenance ([16b8372](https://github.com/srobroek/agentic-scaffold/commit/16b837213b29fd9b8ce84fd78009a2842f4db8f8))
* **release/goreleaser:** publish binaries on the tag release-please pushes ([5137e14](https://github.com/srobroek/agentic-scaffold/commit/5137e1488da43aa1271d1aa34c86f84d65ad8094))
* **release:** mint an App token so the release PR triggers CI ([44873ae](https://github.com/srobroek/agentic-scaffold/commit/44873aee1f8c3fae6a801a8f369f7cb9e9a31c08))
* **release:** port release-please and dep-updates, add cocogitto ([cc979b6](https://github.com/srobroek/agentic-scaffold/commit/cc979b676de9aaeb7cc48fa6303fd052ee16bf54))
* **release:** sync the marketplace catalogs onto the release branch ([437f4df](https://github.com/srobroek/agentic-scaffold/commit/437f4dfb3348689cc65ac966cc53d72ec0347234))
* split setup and setup-worktree, and copy the dependency trees ([04608ed](https://github.com/srobroek/agentic-scaffold/commit/04608edc7fcdbb28d0d292c9aab43f27a8f6df0c))
* **update-skill:** add project-scaffold-update ([1177f75](https://github.com/srobroek/agentic-scaffold/commit/1177f758f15665a7dcc81c654cceccfffccbffb8))
* **workspace/just:** port the task-surface layer ([df04169](https://github.com/srobroek/agentic-scaffold/commit/df04169b319131b4a477a75f4a20f7d516054170))
* **workspace/monorepo:** add the workspace layer and just add ([b874718](https://github.com/srobroek/agentic-scaffold/commit/b87471844b38d82f63e1604eda3e14db36b5ed06))
* **workspace/moon:** add the member graph layer ([a5d7b07](https://github.com/srobroek/agentic-scaffold/commit/a5d7b07565570fabfd360d3d4523dab8f1ef3cfa))


### Bug Fixes

* **adr:** open records with frontmatter and keep the index current ([1a382d6](https://github.com/srobroek/agentic-scaffold/commit/1a382d65cc6d8668437d1feee897d639a34724ab))
* **base/gitignore:** take the OS artifacts from gitnr on every render ([a0e1e58](https://github.com/srobroek/agentic-scaffold/commit/a0e1e58f7477a759f990f3d2671388ffb95e5382))
* **cdk:** unset CI for the projen synth, and add a test-ci recipe ([bd738ab](https://github.com/srobroek/agentic-scaffold/commit/bd738ab15663556b37082c1f346cc14157cf526c))
* **ci:** pin apm, let Actions open the release PR, and bound release history ([d51ef3e](https://github.com/srobroek/agentic-scaffold/commit/d51ef3ea306ee33d77eb8e97225bca2a01c6cbfd))
* **ci:** pin the runtimes layers need, and stop two tests depending on this machine ([6f3d85b](https://github.com/srobroek/agentic-scaffold/commit/6f3d85b34169daf4484ada39668b7a25b5518a93))
* **ci:** pin yamllint to a version that exists ([803a52c](https://github.com/srobroek/agentic-scaffold/commit/803a52c56599f059e8c726247f48025210ccacb2))
* exclude filesystem artifacts from every rendered layer ([c8d8a98](https://github.com/srobroek/agentic-scaffold/commit/c8d8a982d8801cd15549a87337ff94ae4fd8dd82))
* **iac/cdk:** keep rationale out of a recipe description ([4001346](https://github.com/srobroek/agentic-scaffold/commit/40013461cb38849d2a76ff32678bb0248e9235b9))
* **index:** derive docs/INDEX.md from tracked files, not the filesystem ([688e64b](https://github.com/srobroek/agentic-scaffold/commit/688e64bb0bbe1d56e31a996f60d0aa1ae2d482e5))
* **lang/api:** state its security posture rather than omitting the fragment ([512b275](https://github.com/srobroek/agentic-scaffold/commit/512b275bfb240c0b6603a7204bf0bde2584a05f5))
* lint this repository's own config, and correct three lying action pins ([8911188](https://github.com/srobroek/agentic-scaffold/commit/8911188cac2cbc00fc8fe116e1bf9508fb1487c2))
* **release:** add package-build, and check for it before syncing ([ca2793e](https://github.com/srobroek/agentic-scaffold/commit/ca2793efcc14bc315cf78df510ff88af860cd850))
* **release:** degrade when the app credentials are absent ([9566eea](https://github.com/srobroek/agentic-scaffold/commit/9566eeadc61ed78092d5525edb9a2b2aab6ffab9))
* **release:** give the repository a release workflow and gate the catalogs ([cb711af](https://github.com/srobroek/agentic-scaffold/commit/cb711affe6eb33a6d7731237572df589a359cc1d))
* **release:** require the app credentials, with no GITHUB_TOKEN fallback ([e4dab30](https://github.com/srobroek/agentic-scaffold/commit/e4dab308d413ef683a353280acb0265735814cd0))
* **release:** scope the App token, and use the real private key ([6a18ff4](https://github.com/srobroek/agentic-scaffold/commit/6a18ff447b3cc09f9cb1fe3b258d7e44ac19ea10))
* **tests:** resolve pinned tools through mise, not an installs/latest path ([0d29846](https://github.com/srobroek/agentic-scaffold/commit/0d298463815c2410cf152bf27808188230a55883))


### Refactors

* **release:** register members in just add, not a sync script ([248cc37](https://github.com/srobroek/agentic-scaffold/commit/248cc37a667a7f357430bc29689e59b17926e108))


### Documentation

* clear the 64 prose-gate errors from the updated vale ruleset ([c697581](https://github.com/srobroek/agentic-scaffold/commit/c69758116dfa44b2b5aa6b5ca2c8c0b206cda1aa))
* drop the gotchas trees ([9bb58f0](https://github.com/srobroek/agentic-scaffold/commit/9bb58f0802886aa66094ef76120cff1044f6549e))
* settle the better-t-stack option defaults ([5b21385](https://github.com/srobroek/agentic-scaffold/commit/5b21385b70f7d6f1534db12585267771a420c729))
