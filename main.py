
import threading
import os
import subprocess
import shlex
import sys
import pty
import select
import fcntl
import termios
import struct
import signal
import errno
import time
import json
from queue import Queue
from datetime import datetime
from kivy.base import runTouchApp
from kivy.event import EventDispatcher
from kivy.lang import Builder
from kivy.properties import ObjectProperty, ListProperty, StringProperty, \
    NumericProperty, Clock, partial, BooleanProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivy.utils import platform
from kivy.app import App
from kivy.core.window import Window
from kivy.uix.behaviors import FocusBehavior
from kivy.metrics import Metrics
Metrics.density = 8 # Increase this for larger font scaling
# Decorator for threaded execution
def run_in_thread(fn):
    """Decorator to run a function in a separate thread."""
    def run(*args, **kwargs):
        thread = threading.Thread(target=fn, args=args, kwargs=kwargs)
        thread.daemon = True
        thread.start()
        return thread
    return run

class TerminalConfig:
    """Handles terminal configuration and persistence."""
    CONFIG_FILE = os.path.expanduser('~/.kivy_console_config')
    
    def __init__(self):
        self.settings = {
            'history_size': 1000,
            'scrollback_lines': 10000,
            'theme': 'dark',
            'font_size': 14,
            'aliases': {},
            'env_vars': {}
        }
        self.load_config()
    
    def load_config(self):
        """Load configuration from file."""
        try:
            if os.path.exists(self.CONFIG_FILE):
                with open(self.CONFIG_FILE, 'r') as f:
                    self.settings.update(json.load(f))
        except Exception as e:
            print(f"Error loading config: {e}")
    
    def save_config(self):
        """Save configuration to file."""
        try:
            with open(self.CONFIG_FILE, 'w') as f:
                json.dump(self.settings, f)
        except Exception as e:
            print(f"Error saving config: {e}")

class CommandHistory:
    """Manages command history with persistence."""
    HISTORY_FILE = os.path.expanduser('~/.kivy_console_history')
    
    def __init__(self, max_size=1000):
        self.history = []
        self.max_size = max_size
        self.position = 0
        self.load_history()
    
    def add(self, command):
        """Add a command to history."""
        if command and (not self.history or command != self.history[-1]):
            self.history.append(command)
            if len(self.history) > self.max_size:
                self.history.pop(0)
            self.save_history()
        self.position = len(self.history)
    
    def get_previous(self):
        """Get previous command from history."""
        if self.position > 0:
            self.position -= 1
            return self.history[self.position]
        return None
    
    def get_next(self):
        """Get next command from history."""
        if self.position < len(self.history) - 1:
            self.position += 1
            return self.history[self.position]
        self.position = len(self.history)
        return ''
    
    def load_history(self):
        """Load history from file."""
        try:
            if os.path.exists(self.HISTORY_FILE):
                with open(self.HISTORY_FILE, 'r') as f:
                    self.history = [line.strip() for line in f.readlines()]
                    self.history = self.history[-self.max_size:]
        except Exception as e:
            print(f"Error loading history: {e}")
    
    def save_history(self):
        """Save history to file."""
        try:
            with open(self.HISTORY_FILE, 'w') as f:
                f.write('\n'.join(self.history))
        except Exception as e:
            print(f"Error saving history: {e}")

class InteractiveProcess:
    """Handles interactive process execution and communication."""
    def __init__(self, command, cwd=None, env=None):
        self.command = command
        self.cwd = cwd or os.getcwd()
        self.env = env or os.environ.copy()
        self.master_fd = None
        self.slave_fd = None
        self.process = None
        self.output_queue = Queue()
        self.is_running = False
        self.last_size = None
        self._setup_terminal()

    def _setup_terminal(self):
        """Setup the pseudo-terminal with proper attributes."""
        self.master_fd, self.slave_fd = pty.openpty()
        
        # Set raw mode
        tty_attr = termios.tcgetattr(self.slave_fd)
        tty_attr[0] = tty_attr[0] & ~(termios.BRKINT | termios.ICRNL | termios.INPCK | termios.ISTRIP | termios.IXON)
        tty_attr[1] = tty_attr[1] & ~termios.OPOST
        tty_attr[2] = tty_attr[2] & ~(termios.CSIZE | termios.PARENB)
        tty_attr[2] = tty_attr[2] | termios.CS8
        tty_attr[3] = tty_attr[3] & ~(termios.ECHO | termios.ICANON | termios.IEXTEN | termios.ISIG)
        termios.tcsetattr(self.slave_fd, termios.TCSANOW, tty_attr)
        
        # Set non-blocking mode for master
        flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
        fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    def update_terminal_size(self, rows, cols):
        """Update the terminal size."""
        size = (rows, cols)
        if size != self.last_size:
            term_size = struct.pack('HHHH', rows, cols, 0, 0)
            try:
                fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, term_size)
                self.last_size = size
            except:
                pass

    def start(self):
        """Start the interactive process."""
        try:
            self.process = subprocess.Popen(
                shlex.split(self.command),
                stdin=self.slave_fd,
                stdout=self.slave_fd,
                stderr=self.slave_fd,
                cwd=self.cwd,
                env=self.env,
                preexec_fn=os.setsid,
                start_new_session=True
            )
            self.is_running = True
            return True
        except Exception as e:
            print(f"Failed to start process: {e}")
            return False

    def read_output(self, timeout=0):
        """Read output from the process with timeout."""
        try:
            if select.select([self.master_fd], [], [], timeout)[0]:
                return os.read(self.master_fd, 4096).decode('utf-8', errors='replace')
        except (OSError, IOError) as e:
            if e.errno != errno.EAGAIN:
                print(f"Error reading output: {e}")
        return None

    def write_input(self, data):
        """Write input to the process."""
        if self.is_running:
            try:
                os.write(self.master_fd, data.encode('utf-8'))
                return True
            except Exception as e:
                print(f"Error writing input: {e}")
        return False

    def terminate(self):
        """Terminate the process and cleanup resources."""
        if self.process:
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                self.process.wait(timeout=1)
            except:
                try:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                except:
                    pass
            self.process = None
        
        self.is_running = False
        try:
            os.close(self.master_fd)
            os.close(self.slave_fd)
        except:
            pass

Builder.load_string('''
<KivyConsole>:
    console_input: console_input
    scroll_view: scroll_view
    BoxLayout:
        orientation: 'vertical'
        ScrollView:
            id: scroll_view
            do_scroll_x: True
            bar_width: 10
            ConsoleInput:
                id: console_input
                shell: root
                size_hint: (1, None)
                height: max(self.parent.height, self.minimum_height)
                font_name: root.font_name
                font_size: root.font_size
                foreground_color: root.foreground_color
                background_color: root.background_color
                multiline: True
                use_bubble: True
                use_handles: True
''')



import os
import shlex
import subprocess
from kivy.clock import Clock
from kivy.app import App

class Shell(EventDispatcher):
    """Main shell class handling command execution and process management."""
    __events__ = ('on_output', 'on_complete', 'on_error')
    
    BUILTIN_COMMANDS = {
        'cd': 'change_directory',
        'clear': 'clear_screen',
        'exit': 'exit_shell',
        'history': 'show_history',
        'help': 'show_help',
        'alias': 'manage_aliases',
        'export': 'export_variable',
        'theme': 'change_theme',
        'python': 'interactive_python',
        'bash': 'interactive_bash'
    }
    
    def __init__(self, **kwargs):
        super(Shell, self).__init__(**kwargs)
        self.interactive_process = None
        self.cur_dir = os.getcwd()
        self._output_check_event = None
        self.config = TerminalConfig()
        self.command_history = CommandHistory(self.config.settings['history_size'])
        self.aliases = self.config.settings['aliases']
        self.env_vars = self.config.settings['env_vars']

    def parse_command(self, command):
        """Parse and preprocess command, handling aliases and variables."""
        parts = shlex.split(command)
        if not parts:
            return command
            
        # Handle aliases
        if parts[0] in self.aliases:
            command = self.aliases[parts[0]] + ' ' + ' '.join(parts[1:])
            
        # Expand environment variables
        command = os.path.expandvars(command)
        return command
    def _move_to_next_line(self, dt=None):
        """Move to the next line after executing a command or pressing Enter with no command."""
        self.dispatch('on_output', "\n")  # Just print a newline to go to the next line
        self.prompt()  # Display the prompt again
    def interactive_python(self, command):
        """Handle interactive python."""
        return "Interactive Python session is not supported in this Kivy terminal.please press enter!"

    def interactive_bash(self, command):
        """Handle interactive bash."""
        return "Not supported.Press enter Twice"




    def run_command(self, command, show_output=True):
        """Execute a command, handling built-ins and external commands."""
        command = command.strip()

        def safe_str(value):
            """Return the string representation of value, handling None."""
            return str(value) if value is not None else ""

        # Check if the command is a built-in or interactive command
        if command in self.BUILTIN_COMMANDS:
            method = getattr(self, self.BUILTIN_COMMANDS[command])
            return method(command)

        # Interactive commands handling without subprocess
        if command in ['bash', 'python']:
            self.dispatch('on_output', f"Output for {command} is: Interactive {command} session is not supported in this Kivy terminal. Please press enter!")
            return

        # Handle misspelled commands like 'pyhton' (e.g., provide an error message)
        if command == 'pyhton':
            self.dispatch('on_output', "Error: Command 'pyhton' not found. Did you mean 'python'?")
            return

        if not command:  # If the command is empty (blank)
            self.dispatch('on_output', '\n')  # Add a newline
            self.prompt()  # Display the prompt again for the next input
            return

        # Add command to history
        self.command_history.add(command)

        # Parse the command
        parsed_command = self.parse_command(command)
        parts = shlex.split(parsed_command)

        # Handle built-in commands (Skip subprocess for these)
        if parts[0] in self.BUILTIN_COMMANDS:
            method = getattr(self, self.BUILTIN_COMMANDS[parts[0]])
            Clock.schedule_once(lambda dt: method(parts[1:]))
            Clock.schedule_once(self.dispatch_complete)  # Ensure completion dispatch
            return

        # Proceed with normal command handling for external commands
        try:
            process = subprocess.Popen(
                parsed_command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                cwd=self.cur_dir,
                text=True,
                bufsize=1,
                universal_newlines=True
            )

            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    output = safe_str(output)  # Ensure output is a valid string
                    Clock.schedule_once(
                        lambda dt, o=output: self.dispatch('on_output', o))

            returncode = process.poll()
            if returncode != 0:
                error = process.stderr.read()
                error = safe_str(error)  # Ensure error is a valid string
                if error:
                    Clock.schedule_once(
                        lambda dt: self.dispatch('on_error', f"Error: {error}\n"))

        except Exception as e:
            # Pass 'e' explicitly to lambda to ensure it has access to the exception object
            Clock.schedule_once(
                lambda dt, e=e: self.dispatch('on_error', f"Error: {str(e)}\n"))
        finally:
            Clock.schedule_once(self.dispatch_complete)  # Dispatch completion



    # Built-in command implementations
    def change_directory(self, args):
        """Change current directory."""
        path = args[0] if args else os.path.expanduser('~')
        try:
            os.chdir(path)
            self.cur_dir = os.getcwd()
            self.dispatch('on_output', f"Changed directory to {self.cur_dir}\n")
        except Exception as e:
            self.dispatch('on_error', f"cd: {str(e)}\n")

    def clear_screen():
        pass
    
    def exit_shell(self, args):
        """Exit the shell."""
        if self.interactive_process:
            self.interactive_process.terminate()
        App.get_running_app().stop()

    def show_history(self, args):
        """Show command history."""
        for i, cmd in enumerate(self.command_history.history, 1):
            self.dispatch('on_output', f"{i:4d}  {cmd}\n")

    def show_help(self, args):
        """Show help information."""
        help_text = """
Available Commands:
  cd [dir]     : Change directory
  clear        : Clear screen
  exit         : Exit shell
  history      : Show command history
  help         : Show this help
  alias        : Manage command aliases
  export       : Set environment variables
  theme        : Change terminal theme

Special Keys:
  Up/Down      : Navigate command history
  Ctrl+C       : Interrupt current process
  Ctrl+D       : End input (EOF)
  Tab          : Auto-complete (where available)
  Ctrl+L       : Clear screen
"""
        self.dispatch('on_output', help_text)

    def manage_aliases(self, args):
        """Manage command aliases."""
        if not args:
            for alias, command in self.aliases.items():
                self.dispatch('on_output', f"alias {alias}='{command}'\n")
        else:
            alias_def = ' '.join(args)
            if '=' in alias_def:
                name, command = alias_def.split('=', 1)
                self.aliases[name.strip()] = command.strip("'\"")
                self.config.save_config()

    def export_variable(self, args):
        """Export environment variables."""
        if not args:
            for key, value in self.env_vars.items():
                self.dispatch('on_output', f"export {key}={value}\n")
        else:
            var_def = ' '.join(args)
            if '=' in var_def:
                name, value = var_def.split('=', 1)
                self.env_vars[name.strip()] = value.strip("'\"")
                os.environ[name.strip()] = value.strip("'\"")
                self.config.save_config()

    def change_theme(self, args):
        """Change terminal theme."""
        themes = {
            'dark': {
                'background': (0, 0, 0, 1),
                'foreground': (1, 1, 1, 1)
            },
            'light': {
                'background': (1, 1, 1, 1),
                'foreground': (0, 0, 0, 1)
            },
            'matrix': {
                'background': (0, 0, 0, 1),
                'foreground': (0, 1, 0, 1)
            },
            'ocean': {
                'background': (0.1, 0.1, 0.3, 1),
                'foreground': (0.8, 0.8, 1, 1)
            }
        }
        
        if not args:
            self.dispatch('on_output', f"Available themes: {', '.join(themes.keys())}\n")
            return
            
        theme_name = args[0]
        if theme_name in themes:
            self.config.settings['theme'] = theme_name
            self.config.save_config()
            self.dispatch('on_output', f"Theme changed to {theme_name}\n")
            Clock.schedule_once(lambda dt: self._apply_theme(themes[theme_name]))
        else:
            self.dispatch('on_error', f"Unknown theme: {theme_name}\n")

    def _apply_theme(self, theme):
        """Apply theme colors to the console."""
        self.parent.background_color = theme['background']
        self.parent.foreground_color = theme['foreground']



import os
import re
from kivy.uix.textinput import TextInput
from kivy.clock import Clock
from kivy.properties import ObjectProperty
import subprocess

class ConsoleInput(TextInput):
    """Enhanced console input with advanced features."""
    shell = ObjectProperty(None)

    def __init__(self, **kwargs):
        kwargs.setdefault('multiline', True)
        kwargs.setdefault('use_bubble', True)
        kwargs.setdefault('use_handles', True)
        super(ConsoleInput, self).__init__(**kwargs)

        self._history = []
        self._history_index = 0
        self._cursor_pos = 0
        self._username = subprocess.run(['whoami'], capture_output=True, text=True).stdout.strip() or 'user'
        self._hostname = subprocess.run(['uname'], capture_output=True, text=True).stdout.strip() or 'localhost'

        self.readonly = False
        Clock.schedule_once(self._initialize, 0)

    def _initialize(self, dt):
        """Initialize console state."""
        if self.shell and hasattr(self.shell, 'cur_dir'):
            self.prompt()
            self.focus = True

    def prompt(self):
        """Display the command prompt."""
        ps1 = f"\n[{self._username}@{self._hostname}@{os.path.basename(self.shell.cur_dir)}]$ "
        self._append_output(ps1)
        self._cursor_pos = len(self.text)

    def _append_output(self, text):
        """Append output text to the console."""
        text = self._clean_output(text)  # Clean the output from escape codes
        self.text += text
        Clock.schedule_once(lambda dt: self._scroll_to_bottom())

    def _scroll_to_bottom(self):
        """Scroll the view to the bottom."""
        if hasattr(self.parent, 'scroll_y'):
            self.parent.scroll_y = 0

    def _clean_output(self, output):
        """Remove ANSI escape codes (for colored text) from the output."""
        return re.sub(r'\x1b\[[0-9;]*m', '', output)

    def keyboard_on_key_down(self, window, keycode, text, modifiers):
        """Handle keyboard input."""
        if keycode[1] == 'enter':
            self._execute_command()
            return True
        elif keycode[1] == 'backspace':
            if self.cursor_index() <= self._cursor_pos:
                return True
        elif 'ctrl' in modifiers:
            if keycode[1] == 'c':
                self._handle_interrupt()
                return True

        return super(ConsoleInput, self).keyboard_on_key_down(window, keycode, text, modifiers)

    def _execute_command(self):
        """Execute the current command."""
        command = self._get_current_command().strip()
        if not command:
            self._append_output("\n")  # Ensure new line on blank input
            self.prompt()
            return
        # Execute command as usual
        self._history.append(command)
        self._history_index = len(self._history)
        self._append_output(f"\n")
        if self.shell.interactive_process and self.shell.interactive_process.is_runnping:
            self.shell.interactive_process.write_input(command + '\n')
        else:
            try:
                output = self.shell.run_command(command)
                output = f"\n Output for {command} is: {str(output)}" if output is not None else f"Output for {command} is:"

                # Check if output is a thread, and wait for it to finish if it is
                if isinstance(output, threading.Thread):
                    output.join()  # Wait for the thread to finish
                    output = str(output)  # Convert thread to string for display
                elif isinstance(output, subprocess.Popen):
                    output = output.communicate()[0].decode()  # Capture output from Popen
                self._append_output(output + "\n")
            except Exception as e:
                self._append_output(f"Error: {str(e)}\n")


    def _get_current_command(self):
        """Get the current command being typed."""
        return self.text[self._cursor_pos:].strip()

    def _handle_interrupt(self):
        """Handle Ctrl+C interrupt."""
        self._append_output("^C\n")
        self.prompt()

    def cursor_index(self, cursor=None):
        """Get cursor index and ensure it doesn't go before the prompt."""
        if cursor is None:
            cursor = self.cursor
        return max(self._cursor_pos, super(ConsoleInput, self).cursor_index(cursor))

    def do_backspace(self, from_undo=False, mode='bkspc'):
        """Prevent backspace from deleting prompt."""
        if self.cursor_index() <= self._cursor_pos:
            return
        return super(ConsoleInput, self).do_backspace(from_undo, mode)

    def keyboard_on_key_up(self, window, keycode):
        """Handle key release events."""
        return super(ConsoleInput, self).keyboard_on_key_up(window, keycode)


class KivyConsole(BoxLayout, Shell):
    """Main console widget combining UI and shell functionality."""
    
    console_input = ObjectProperty(None)
    scroll_view = ObjectProperty(None)
    foreground_color = ListProperty((1, 1, 1, 1))
    background_color = ListProperty((0, 0, 0, 1))
    font_name = StringProperty('monospace')
    font_size = NumericProperty(14)
    
    def __init__(self, **kwargs):
        # Initialize BoxLayout first
        BoxLayout.__init__(self, **kwargs)
        
        # Initialize Shell second
        Shell.__init__(self)
        
        # Bind events
        self.bind(size=self._update_console_size)
        Window.bind(on_resize=self._update_console_size)
        
        # Load saved theme
        self._load_theme()
        
        # Schedule initial focus
        Clock.schedule_once(self._focus_input)

    def _load_theme(self):
        """Load the saved theme from config."""
        theme_name = self.config.settings.get('theme', 'dark')
        themes = {
            'dark': {
                'background': (0, 0, 0, 1),
                'foreground': (1, 1, 1, 1)
            },
            'light': {
                'background': (1, 1, 1, 1),
                'foreground': (0, 0, 0, 1)
            },
            'matrix': {
                'background': (0, 0, 0, 1),
                'foreground': (0, 1, 0, 1)
            },
            'ocean': {
                'background': (0.1, 0.1, 0.3, 1),
                'foreground': (0.8, 0.8, 1, 1)
            }
        }
        
        if theme_name in themes:
            self.background_color = themes[theme_name]['background']
            self.foreground_color = themes[theme_name]['foreground']

    def dispatch_complete(self, dt=None):
        """Dispatch the on_complete event to signal command completion."""
        self.dispatch('on_complete', 'Command execution completed.')

    def _focus_input(self, dt):
        """Focus the input field."""
        if self.console_input:
            self.console_input.focus = True

    def _update_console_size(self, *args):
        """Update terminal size when window is resized."""
        if not self.console_input:
            return
            
        # Calculate terminal dimensions based on font size and window size
        rows = int(self.height / (self.font_size * 1.5))
        cols = int(self.width / (self.font_size * 0.6))
        
        # Update terminal size if there's an active process
        if self.interactive_process:
            self.interactive_process.update_terminal_size(rows, cols)

    def on_output(self, output):
        """Handle output from the shell."""
        if self.console_input:
            self.console_input.text += output
            self._scroll_to_bottom()

    def on_error(self, error):
        """Handle error output from the shell."""
        if self.console_input:
            self.console_input.text += f"\033[91m{error}\033[0m"  # Red color for errors
            self._scroll_to_bottom()

    def on_complete(self, *args):
        """Handle command completion."""
        if not (self.interactive_process and self.interactive_process.is_running):
            if self.console_input:
                self.console_input.prompt()

    def _scroll_to_bottom(self, *args):
        """Scroll the view to the bottom."""
        if self.scroll_view:
            self.scroll_view.scroll_y = 0

class KivyConsoleApp(App):
    def build(self):
        """Build and return the root widget."""
        # Set window title
        self.title = 'Kivy Terminal'
        
        # Create the console
        console = KivyConsole()
        
        # Bind keyboard shortcuts
        Window.bind(on_key_down=self._on_keyboard)
        
        return console

    def _on_keyboard(self, window, key, *args):
        """Global keyboard handler."""
        if args[-1] == ['ctrl'] and key == 27:  # Ctrl+Esc
            self.stop()
            return True
        return False

def main():
    """Main entry point."""
    try:
        app = KivyConsoleApp()
        app.run()
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
