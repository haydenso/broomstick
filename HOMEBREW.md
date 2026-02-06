# Homebrew Installation Guide

This guide explains how to install Broomstick via Homebrew and how to set up your own Homebrew tap.

## For Users: Installing Broomstick

### Quick Install

```bash
# Install directly from the formula
brew install https://raw.githubusercontent.com/haydenso/broomstick/main/broomstick.rb
```

### Install from Tap (Recommended after tap is created)

```bash
# Add the tap
brew tap haydenso/broomstick

# Install broomstick
brew install broomstick

# Verify installation
broomstick --help
```

### Updating

```bash
# Update Homebrew
brew update

# Upgrade broomstick
brew upgrade broomstick
```

### Uninstalling

```bash
brew uninstall broomstick
```

## For Maintainers: Creating a Homebrew Tap

### Step 1: Create a GitHub Repository

Create a new repository named `homebrew-broomstick` at:
```
https://github.com/haydenso/homebrew-broomstick
```

### Step 2: Add the Formula

1. Create a `Formula` directory in the repository
2. Copy `broomstick.rb` to `Formula/broomstick.rb`

### Step 3: Create a Release

1. Create a git tag for the release:
```bash
git tag -a v2.0.0 -m "Release v2.0.0"
git push origin v2.0.0
```

2. Create a tarball:
```bash
git archive --format=tar.gz --prefix=broomstick-2.0.0/ v2.0.0 > broomstick-2.0.0.tar.gz
```

3. Calculate the SHA256:
```bash
shasum -a 256 broomstick-2.0.0.tar.gz
```

4. Update the `sha256` field in `broomstick.rb` with the calculated hash

### Step 4: Test the Formula Locally

```bash
# Audit the formula
brew audit --new-formula broomstick.rb

# Test installation
brew install --build-from-source ./broomstick.rb

# Test the installation
broomstick --help

# Uninstall
brew uninstall broomstick
```

### Step 5: Publish the Tap

Push the `homebrew-broomstick` repository to GitHub:

```bash
cd homebrew-broomstick
git add Formula/broomstick.rb
git commit -m "Add broomstick formula v2.0.0"
git push origin main
```

Now users can install with:
```bash
brew tap haydenso/broomstick
brew install broomstick
```

## Updating the Formula for New Releases

When releasing a new version:

1. Create a new git tag (e.g., v2.1.0)
2. Generate the tarball
3. Calculate the new SHA256
4. Update the formula:
   - Change the `version` line (or it's derived from the URL)
   - Update the `url` to point to the new tarball
   - Update the `sha256` with the new hash
5. Test the updated formula
6. Commit and push to `homebrew-broomstick`

## Alternative: Submit to Homebrew Core

To get broomstick into the main Homebrew repository:

1. Ensure broomstick is stable and well-tested
2. Meet [Homebrew's acceptable formulae criteria](https://docs.brew.sh/Acceptable-Formulae)
3. Create a pull request to [homebrew-core](https://github.com/Homebrew/homebrew-core)
4. Follow the [contributing guidelines](https://docs.brew.sh/Formula-Cookbook)

## Troubleshooting

### Formula Not Found
```bash
# Make sure you've added the tap
brew tap haydenso/broomstick

# Or use the full formula path
brew install haydenso/broomstick/broomstick
```

### Installation Failed
```bash
# Try building from source
brew install --build-from-source haydenso/broomstick/broomstick

# Check the logs
brew gist-logs broomstick
```

### Permission Issues
```bash
# Fix Homebrew permissions
sudo chown -R $(whoami) $(brew --prefix)/*
```

## Resources

- [Homebrew Documentation](https://docs.brew.sh/)
- [Formula Cookbook](https://docs.brew.sh/Formula-Cookbook)
- [Python for Formula Authors](https://docs.brew.sh/Python-for-Formula-Authors)
- [How to Create Your Own Tap](https://docs.brew.sh/How-to-Create-and-Maintain-a-Tap)
