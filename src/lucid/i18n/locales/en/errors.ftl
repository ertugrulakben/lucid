### Error messages — short, actionable, never leaks secrets.

# Configuration / setup
err-no-api-key = No API key configured. Run `lucid setup` or set ANTHROPIC_API_KEY.
err-bad-config = Configuration file could not be parsed: { $path }
err-bad-locale = Unknown locale: { $locale }. Falling back to English.

# Backend / network
err-backend-unreachable = Cannot reach the configured backend ({ $backend }).
err-backend-timeout = Backend did not respond within { $seconds }s.
err-backend-rate-limit = Rate limit reached. Retrying in { $seconds }s.
err-backend-auth = Backend rejected the credentials. Check your API key.

# Capture / desktop
err-capture-failed = Could not capture the screen: { $reason }
err-window-not-found = Window not found: { $title }
err-element-not-found = Element not found: { $description }

# Execution / safety
err-step-failed = Step failed: { $reason }
err-budget-exceeded = Step or time budget exceeded.
err-user-stopped = Stopped by the user.
err-permission-denied = Permission denied: { $resource }

# Workflow / replay
err-workflow-not-found = No workflow matching: { $name }
err-workflow-corrupt = Workflow file is corrupt: { $path }
err-template-missing-var = Template variable not provided: { $name }

# Generic
err-unexpected = Unexpected error: { $reason }
err-not-implemented = Not implemented yet: { $feature }
