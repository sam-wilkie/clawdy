"""clawd_tank_daemon package.

Re-exports the per-agent hook payload converters so callers can import them from
the package root (the bridge script in ``clawd_tank_menubar/hooks.py`` keeps an
inlined copy, but the daemon and its tests import the canonical version here).
"""

from .opencode_protocol import opencode_hook_payload_to_daemon_message

__all__ = ["opencode_hook_payload_to_daemon_message"]