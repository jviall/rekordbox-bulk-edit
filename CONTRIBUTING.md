# Contributing to Rekordbox Bulk Edit

Thanks for your interest in contributing to this project! I am by no means a python developer by nature, so I'm eager for more seasoned devs to weigh in, but one way or another, I hope you're here as a fellow DJ looking to make managing a RekordBox library easier :)

## Development Setup

### Prerequisites

- Python 3.11+
- Poetry for dependency management

### Installation

1. **Install Poetry** (if not already installed):

   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   ```

2. **Clone the repository**:

   ```bash
   git clone https://github.com/jviall/rekordbox-bulk-edit.git
   cd rekordbox-bulk-edit
   ```

3. **Install the project and dependencies**:

   ```bash
   poetry install --with dev
   ```

4. **Activate the virtual environment**:

   ```bash
   eval $(poetry env activate)
   ```

   _or_

   ```Powershell
   Invoke-Expression (poetry env activate)
   ```

5. Install `pre-commit` hooks

   ```bash
   pre-commit install
   ```

6. **Verify installation**:
   ```bash
   rekordbox-bulk-edit --version
   ```

### Tasks (via poethepoet)

```bash
# Run tests with coverage
poe test

# Run linting and auto-fix issues
poe lint

# Run all pre-commit hooks on all files
poe run-hooks
```

### Managing Dependencies

```bash
# Add a new runtime dependency
poetry add package-name

# Add a new development dependency
poetry add --group dev package-name

# Update dependencies
poetry update

# Show dependency tree
poetry show --tree
```

### Building and Publishing

```bash
# Build the package
poetry build

# Check the built package
poetry run twine check dist/*

# Publish to PyPI (requires authentication)
poetry publish
```

## Commit Convention

This project uses [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).
