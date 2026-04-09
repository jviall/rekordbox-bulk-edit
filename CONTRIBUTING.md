# Contributing to Rekordbox Bulk Edit

Thanks for your interest in contributing to this project! I am by no means a python developer by nature, so I'm eager for more seasoned devs to weigh in, but one way or another, I hope you're here as a fellow DJ looking to make managing a RekordBox library easier :)

## Development Setup

### Prerequisites

- Python 3.10+
- [UV](https://docs.astral.sh/uv/) for dependency management

### Installation

1. **Install UV** (if not already installed):

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Clone the repository**:

   ```bash
   git clone https://github.com/jviall/rekordbox-bulk-edit.git
   cd rekordbox-bulk-edit
   ```

3. **Install the project and dependencies**:

   ```bash
   uv sync
   ```

4. **Activate the virtual environment**:

   ```bash
   source .venv/bin/activate    # macOS/Linux
   ```

   _or_

   ```Powershell
   .venv\Scripts\activate       # Windows
   ```

5. Install `pre-commit` hooks

   ```bash
   pre-commit install
   ```

6. **Verify installation**:
   ```bash
   rekordbox-bulk-edit --version
   ```

### Tasks (via Make)

```bash
# Run tests
make test

# Run tests with coverage
make coverage

# Run linting and auto-fix issues
make lint

# Run formatting
make format

# Run all pre-commit hooks on all files
make run-hooks
```

### Managing Dependencies

```bash
# Add a new runtime dependency
uv add package-name

# Add a new development dependency
uv add --group dev package-name

# Update dependencies
uv lock --upgrade

# Show dependency tree
uv tree
```

### Building and Publishing

```bash
# Build the package
uv build

# Publish to PyPI (requires authentication)
uv publish
```

## Commit Convention

This project uses [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).
