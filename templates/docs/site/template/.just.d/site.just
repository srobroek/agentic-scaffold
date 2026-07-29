# Documentation site recipes, imported by the root justfile.

# Install the site's dependencies
[group('docs')]
site-install:
    cd docs/site && bun install --frozen-lockfile

# Serve the site with live reload
[group('docs')]
site-dev:
    cd docs/site && bun run dev

# Build the site into docs/site/dist
[group('docs')]
site-build:
    cd docs/site && bun run build

# Serve the built output, as the deploy would
[group('docs')]
site-preview:
    cd docs/site && bun run preview
