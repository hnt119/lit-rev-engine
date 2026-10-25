"""Local OS security boundary; research contracts and ranking stay OS-neutral."""
from .files import (IS_WINDOWS, assert_no_links, is_link, open_private, owned_fd,
                    owned_path, private_directory, restrict_fd, restrict_path,
                    current_user_key, is_process_alive, venv_python,
                    atomic_replace, publish_new, sync_directory)
