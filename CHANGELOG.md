# Changelog

## [2.0.0] - 2024-01-18

### Added
- Complete project restructure with professional package organization
- Unified CLI interface with `yt-organizer` command
- Comprehensive test suite with pytest
- Type hints throughout the codebase with Pydantic models
- Rich terminal output with progress bars and formatted tables
- Batch processing capabilities for performance optimization
- Caching layer for API responses
- Pre-commit hooks for code quality
- CI/CD pipeline with GitHub Actions
- Architecture documentation
- Progress tracking that persists across sessions
- Dry-run mode for testing without making changes

### Changed
- Migrated from scripts to package-based architecture
- Replaced print statements with professional logging
- Centralized configuration management with validation
- Eliminated ~70% code duplication with shared base modules
- Improved error handling with custom exception hierarchy
- Enhanced browser automation with better error recovery

### Fixed
- Tab/space inconsistencies in code
- Pydantic v2 compatibility issues
- Import organization and circular dependencies

### Deprecated
- Old script-based interface (compatibility wrappers provided)

## [1.0.0] - Previous Version

### Features
- Basic YouTube Watch Later organization
- Gemini AI classification
- Browser automation with Playwright
- OAuth authentication
- Multiple operation scripts
