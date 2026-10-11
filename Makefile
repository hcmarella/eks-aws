.PHONY: test run docker local-up lint-yaml
test: ; cd app && python -m pytest -q
run: ; cd app && MODEL_RUNNER=replay python cli.py
docker: ; docker build -t conductor:local .
local-up: ; ./scripts/local-up.sh
lint-yaml: ; python3 -c "import yaml,glob;[list(yaml.safe_load_all(open(f))) for f in glob.glob('argocd/*.yaml')+glob.glob('k8s/**/*.yaml',recursive=True)+glob.glob('helm/conductor/values*.yaml')+glob.glob('.github/workflows/*.yml')]"
