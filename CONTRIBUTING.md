# Contributing Guide

Thanks for contributing to 41chan! 🎉

## Issues

- **Bug Reports**: Please use the [Bug Report template](.github/ISSUE_TEMPLATE/bug_report.md)
- **Feature Requests**: Please use the [Feature Request template](.github/ISSUE_TEMPLATE/feature_request.md)
- Issues in English are welcome.

## Pull Requests

1. Fork the repository
2. Create a branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m "feat: add something"`
4. Push: `git push origin feature/your-feature`
5. Open a Pull Request

### Branch Naming Convention

| Prefix | Purpose |
|------------|------|
| `feature/` | New features |
| `fix/` | Bug fixes |
| `docs/` | Documentation |
| `refactor/` | Refactoring |
| `chore/` | Maintenance (dependency updates, etc.) |

### Commit Messages

Please follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: description of new feature
fix: description of bug fix
docs: documentation changes
refactor: refactoring
chore: maintenance
```

## Code Style

### Python (backend/)

- Formatter: [black](https://github.com/psf/black)
- Linter: [ruff](https://github.com/astral-sh/ruff)
- Type hints recommended

```bash
cd backend
pip install black ruff
black .
ruff check .
```

### TypeScript (frontend/)

- Formatter: [Prettier](https://prettier.io/)
- Linter: ESLint (Next.js config)

```bash
cd frontend
npm run lint
```

## Testing LLM Backends

### Testing with Ollama (local)

```bash
# Start Ollama
export OLLAMA_NUM_PARALLEL=4
ollama serve

# Download a model
ollama pull qwen3.5:9b

# Start with Ollama backend
ORACLE_LLM_BACKEND=ollama venv/bin/uvicorn main:app --reload --port 8001
```

### Testing with ZAI/OpenRouter

```bash
# Set your API key in .env, then:
ORACLE_LLM_BACKEND=zai venv/bin/uvicorn main:app --reload --port 8001
```

### Test Simulations

- Select "mini" scale in the frontend (5 agents, lower API usage)
- Try a simple theme (e.g., "The future of AI and education")

## Directory Structure

- `backend/core/` — Core logic (LLM, agent generation, simulation)
- `backend/api/` — FastAPI routers
- `backend/services/` — Business logic
- `frontend/app/` — Next.js pages
- `frontend/components/` — React components
- `docs/` — Documentation

## Questions

Feel free to open an issue if you have any questions.
