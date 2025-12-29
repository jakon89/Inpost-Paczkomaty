# [0.3.0](https://github.com/jakon89/Inpost-Paczkomaty/compare/v0.2.0...v0.3.0) (2025-12-29)


### Features

* **auth:** Replace external authentication with direct InPost OAuth2 flow ([#12](https://github.com/jakon89/Inpost-Paczkomaty/issues/12))
* **auth:** Add PKCE-based OAuth2 authentication with InPost API
* **auth:** Store access_token and refresh_token for authenticated API calls
* **auth:** Add email confirmation step for existing InPost accounts
* **auth:** Support multi-language authentication flow (Polish/English[default])


### Breaking Changes

* Authentication now uses InPost's official OAuth2 flow instead of external service
* Config entry data structure changed - existing integrations will need to be re-configured


# [0.2.0](https://github.com/jakon89/Inpost-Paczkomaty/compare/v0.1.0...v0.2.0) (2025-11-19)


### Features

* add phone number to sensor names ([d17eaf5](https://github.com/jakon89/Inpost-Paczkomaty/commit/d17eaf502c1a4ae7cb1a4ff15574580e9dfbea44))
* Handle backend rate limiting and show proper error messages ([9d8ce5b](https://github.com/jakon89/Inpost-Paczkomaty/commit/9d8ce5bde73e4ebbc9079788b18e48c7032a4735))

# [0.1.0](https://github.com/jakon89/Inpost-Paczkomaty/compare/v0.0.0...v0.1.0) (2025-11-19)


### Features

* force minor release ([fd8695e](https://github.com/jakon89/Inpost-Paczkomaty/commit/fd8695e8bc41d0b5f4794bfee320333cf572f319))

# [0.1.0](https://github.com/jakon89/Inpost-Paczkomaty/compare/v0.0.0...v0.1.0) (2025-11-16)


### Features

* test ([2ec7e30](https://github.com/jakon89/Inpost-Paczkomaty/commit/2ec7e30780459865b60195894eb4887bd0cb40d5))
