#!/usr/bin/env python3
"""
Git Auto-Sync Monitor
A background application that monitors .lpz files and automatically syncs changes to Git.
Features:
- System tray integration
- Automatic file monitoring
- Git operations (add, commit, push, pull, fetch)
- Configurable paths and settings
"""

import os
import sys
import threading
import time
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
from datetime import datetime

# Third-party imports (install with: pip install watchdog pystray pillow)
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    import pystray
    from PIL import Image, ImageDraw
except ImportError as e:
    print(f"Missing required packages. Please install with:")
    print("pip install watchdog pystray pillow")
    sys.exit(1)


class LpzFileHandler(FileSystemEventHandler):
    """Handles .lpz file change events"""
    
    def __init__(self, app):
        self.app = app
        self.last_event_time = {}
        
    def on_modified(self, event):
        if event.is_directory:
            return
            
        if event.src_path.endswith('.lpz'):
            # Debounce events (ignore if same file modified within 3 seconds)
            now = time.time()
            if event.src_path in self.last_event_time:
                if now - self.last_event_time[event.src_path] < 3:
                    return
            
            self.last_event_time[event.src_path] = now
            print(f"Detected change in: {event.src_path}")
            
            # Schedule the commit dialog on the main thread with file path captured
            file_path = event.src_path
            self.app.root.after(100, lambda fp=file_path: self.app.show_commit_dialog(fp))


class GitAutoSyncApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Git Auto-Sync Monitor")
        self.root.geometry("500x300")
        
        # Configuration
        self.config_file = "git_sync_config.json"
        self.config = self.load_config()
        
        # File monitoring
        self.observer = None
        self.monitoring = False
        self.active_dialog = None  # Track active commit dialog
        
        # System tray
        self.tray_icon = None
        
        # Setup GUI
        self.setup_main_gui()
        
        # Load existing config if available
        if self.config.get('watch_path') and self.config.get('repo_path'):
            self.watch_path_var.set(self.config['watch_path'])
            self.repo_path_var.set(self.config['repo_path'])
            self.remote_var.set(self.config.get('default_remote', 'origin'))
            self.branch_var.set(self.config.get('default_branch', 'main'))
        
        # Handle window close event
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
    def load_config(self):
        """Load configuration from JSON file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
        return {}
    
    def save_config(self):
        """Save configuration to JSON file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def setup_main_gui(self):
        """Setup the main configuration GUI"""
        # Main frame
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Title
        title_label = ttk.Label(main_frame, text="Git Auto-Sync Monitor", 
                               font=('Arial', 16, 'bold'))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # Watch Path
        ttk.Label(main_frame, text="📂 Path to Watch:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.watch_path_var = tk.StringVar()
        watch_entry = ttk.Entry(main_frame, textvariable=self.watch_path_var, width=40)
        watch_entry.grid(row=1, column=1, padx=(10, 5), pady=5)
        ttk.Button(main_frame, text="Browse", 
                  command=self.browse_watch_path).grid(row=1, column=2, pady=5)
        
        # Repository Path
        ttk.Label(main_frame, text="📁 Git Repository:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.repo_path_var = tk.StringVar()
        repo_entry = ttk.Entry(main_frame, textvariable=self.repo_path_var, width=40)
        repo_entry.grid(row=2, column=1, padx=(10, 5), pady=5)
        ttk.Button(main_frame, text="Browse", 
                  command=self.browse_repo_path).grid(row=2, column=2, pady=5)
        
        # Default Remote
        ttk.Label(main_frame, text="🔗 Default Remote:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.remote_var = tk.StringVar(value="origin")
        ttk.Entry(main_frame, textvariable=self.remote_var, width=20).grid(row=3, column=1, 
                                                                          sticky=tk.W, padx=(10, 5), pady=5)
        
        # Default Branch
        ttk.Label(main_frame, text="🌿 Default Branch:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.branch_var = tk.StringVar(value="main")
        ttk.Entry(main_frame, textvariable=self.branch_var, width=20).grid(row=4, column=1, 
                                                                          sticky=tk.W, padx=(10, 5), pady=5)
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=5, column=0, columnspan=3, pady=20)
        
        ttk.Button(button_frame, text="Start Monitoring", 
                  command=self.start_monitoring).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Minimize to Tray", 
                  command=self.minimize_to_tray).pack(side=tk.LEFT, padx=5)
        
        # Status
        self.status_var = tk.StringVar(value="Ready to start monitoring...")
        ttk.Label(main_frame, textvariable=self.status_var, 
                 font=('Arial', 9), foreground='gray').grid(row=6, column=0, columnspan=3, pady=10)
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
    def browse_watch_path(self):
        """Browse for watch directory"""
        path = filedialog.askdirectory(title="Select Directory to Watch")
        if path:
            self.watch_path_var.set(path)
            
    def browse_repo_path(self):
        """Browse for repository directory"""
        path = filedialog.askdirectory(title="Select Git Repository Directory")
        if path:
            self.repo_path_var.set(path)
    
    def start_monitoring(self):
        """Start file monitoring"""
        watch_path = self.watch_path_var.get().strip()
        repo_path = self.repo_path_var.get().strip()
        
        if not watch_path or not repo_path:
            messagebox.showerror("Error", "Please specify both watch path and repository path")
            return
            
        if not os.path.exists(watch_path):
            messagebox.showerror("Error", f"Watch path does not exist: {watch_path}")
            return
            
        if not os.path.exists(repo_path):
            messagebox.showerror("Error", f"Repository path does not exist: {repo_path}")
            return
            
        if not os.path.exists(os.path.join(repo_path, '.git')):
            messagebox.showerror("Error", f"Not a Git repository: {repo_path}")
            return
        
        # Save configuration
        self.config.update({
            'watch_path': watch_path,
            'repo_path': repo_path,
            'default_remote': self.remote_var.get(),
            'default_branch': self.branch_var.get()
        })
        self.save_config()
        
        # Start monitoring
        try:
            if self.observer:
                self.observer.stop()
                
            self.observer = Observer()
            event_handler = LpzFileHandler(self)
            self.observer.schedule(event_handler, watch_path, recursive=True)
            self.observer.start()
            
            self.monitoring = True
            self.status_var.set(f"Monitoring: {watch_path}")
            messagebox.showinfo("Success", "Monitoring started successfully!")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start monitoring: {e}")
    
    def show_commit_dialog(self, file_path):
        """Show commit dialog when file changes"""
        # Prevent multiple dialogs
        if self.active_dialog:
            try:
                if self.active_dialog.winfo_exists():
                    print("Commit dialog already open, ignoring new change event")
                    return
            except tk.TclError:
                # Dialog no longer exists, clear reference
                self.active_dialog = None
        
        print(f"Creating commit dialog for: {os.path.basename(file_path)}")
            
        try:
            # Create dialog with proper error handling
            if not self.root.winfo_viewable():
                # Main window is hidden, create independent dialog
                dialog_obj = CommitDialog(None, self, file_path)
                self.active_dialog = dialog_obj.dialog
            else:
                # Main window is visible, use it as parent
                dialog_obj = CommitDialog(self.root, self, file_path)
                self.active_dialog = dialog_obj.dialog
        except Exception as e:
            print(f"Error creating commit dialog: {e}")
            # Try again with no parent as fallback
            try:
                dialog_obj = CommitDialog(None, self, file_path)
                self.active_dialog = dialog_obj.dialog
            except Exception as e2:
                print(f"Failed to create commit dialog: {e2}")
                self.active_dialog = None
        
    def minimize_to_tray(self):
        """Minimize application to system tray"""
        if not self.monitoring:
            messagebox.showwarning("Warning", "Please start monitoring before minimizing to tray")
            return
            
        self.root.withdraw()  # Hide the main window
        
        # Only create tray icon if it doesn't exist
        if not self.tray_icon:
            self.create_tray_icon()
        
    def create_tray_icon(self):
        """Create system tray icon"""
        # Create a simple icon
        image = Image.new('RGB', (64, 64), color='blue')
        draw = ImageDraw.Draw(image)
        draw.ellipse([16, 16, 48, 48], fill='white')
        draw.text((28, 26), "G", fill='blue')
        
        # Create menu
        menu = pystray.Menu(
            pystray.MenuItem("🛠 Open Config", self.show_main_window),
            pystray.MenuItem("🔄 Force Push Now", self.force_push),
            pystray.MenuItem("⬇️ Git Pull", self.git_pull),
            pystray.MenuItem("🔃 Git Fetch", self.git_fetch),
            pystray.MenuItem("❌ Exit", self.quit_app)
        )
        
        self.tray_icon = pystray.Icon("git_sync", image, "Git Auto-Sync Monitor", menu)
        
        # Run tray icon in separate thread
        threading.Thread(target=self.tray_icon.run, daemon=True).start()
        
    def show_main_window(self, icon=None, item=None):
        """Show the main configuration window"""
        self.root.deiconify()
        self.root.lift()
        self.root.attributes('-topmost', True)  # Bring to front
        self.root.after(100, lambda: self.root.attributes('-topmost', False))  # Remove topmost after brief moment
        
    def force_push(self, icon=None, item=None):
        """Force push current changes"""
        if not self.config.get('repo_path'):
            self.show_tray_message("Error", "❌ No repository configured")
            return
        
        def run_push():
            try:
                success = self.run_git_commands(
                    self.config['repo_path'],
                    "Manual push from tray",
                    self.config.get('default_remote', 'origin'),
                    self.config.get('default_branch', 'main')
                )
                
                if success:
                    self.root.after(0, lambda: self.show_tray_message("Success", "✅ Force push completed successfully!"))
                else:
                    self.root.after(0, lambda: self.show_tray_message("Error", "❌ Force push failed. Check console for details."))
                    
            except Exception as e:
                print(f"Force push failed: {e}")
                self.root.after(0, lambda: self.show_tray_message("Error", f"❌ Force push error: {str(e)}"))
        
        # Show initial message and run in background
        self.show_tray_message("Info", "🔄 Force pushing changes...")
        threading.Thread(target=run_push, daemon=True).start()
            
    def git_pull(self, icon=None, item=None):
        """Perform git pull"""
        if not self.config.get('repo_path'):
            self.show_tray_message("Error", "❌ No repository configured")
            return
        
        def run_pull():
            try:
                result = subprocess.run(
                    ['git', 'pull'],
                    cwd=self.config['repo_path'],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    if "Already up to date" in result.stdout or "Already up-to-date" in result.stdout:
                        message = "✅ Repository is already up to date"
                    elif "Fast-forward" in result.stdout or "files changed" in result.stdout:
                        message = "✅ Pull completed - repository updated!"
                    else:
                        message = "✅ Pull completed successfully"
                    
                    self.root.after(0, lambda: self.show_tray_message("Git Pull", message))
                else:
                    error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                    self.root.after(0, lambda: self.show_tray_message("Error", f"❌ Pull failed: {error_msg}"))
                
                print(f"Git pull result: {result.stdout}")
                if result.stderr:
                    print(f"Git pull error: {result.stderr}")
                    
            except subprocess.TimeoutExpired:
                self.root.after(0, lambda: self.show_tray_message("Error", "❌ Pull timed out (>30 seconds)"))
            except Exception as e:
                print(f"Git pull failed: {e}")
                self.root.after(0, lambda: self.show_tray_message("Error", f"❌ Pull error: {str(e)}"))
        
        # Show initial message and run in background
        self.show_tray_message("Info", "🔄 Pulling latest changes...")
        threading.Thread(target=run_pull, daemon=True).start()
            
    def git_fetch(self, icon=None, item=None):
        """Perform git fetch"""
        if not self.config.get('repo_path'):
            self.show_tray_message("Error", "❌ No repository configured")
            return
        
        def run_fetch():
            try:
                result = subprocess.run(
                    ['git', 'fetch'],
                    cwd=self.config['repo_path'],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    if result.stdout.strip():
                        message = "✅ Fetch completed - new changes available"
                    else:
                        message = "✅ Fetch completed - no new changes"
                    
                    self.root.after(0, lambda: self.show_tray_message("Git Fetch", message))
                else:
                    error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                    self.root.after(0, lambda: self.show_tray_message("Error", f"❌ Fetch failed: {error_msg}"))
                
                print(f"Git fetch result: {result.stdout}")
                if result.stderr:
                    print(f"Git fetch error: {result.stderr}")
                    
            except subprocess.TimeoutExpired:
                self.root.after(0, lambda: self.show_tray_message("Error", "❌ Fetch timed out (>30 seconds)"))
            except Exception as e:
                print(f"Git fetch failed: {e}")
                self.root.after(0, lambda: self.show_tray_message("Error", f"❌ Fetch error: {str(e)}"))
        
        # Show initial message and run in background
        self.show_tray_message("Info", "🔄 Fetching latest changes...")
        threading.Thread(target=run_fetch, daemon=True).start()
    
    def show_tray_message(self, title, message):
        """Show popup message for tray operations"""
        # Create a temporary window to ensure messagebox appears on top
        temp = tk.Toplevel()
        temp.withdraw()
        temp.attributes('-topmost', True)
        
        # Determine message type and show appropriate dialog
        if title == "Error" or "❌" in message:
            messagebox.showerror(title, message, parent=temp)
        elif title == "Success" or "✅" in message:
            messagebox.showinfo(title, message, parent=temp)
        else:
            messagebox.showinfo(title, message, parent=temp)
        
        temp.destroy()
    
    def run_git_commands(self, repo_path, commit_message, remote, branch):
        """Run git add, commit, and push commands"""
        try:
            # Git add
            subprocess.run(['git', 'add', '.'], cwd=repo_path, check=True)
            
            # Git commit
            subprocess.run(['git', 'commit', '-m', commit_message], cwd=repo_path, check=True)
            
            # Git push
            subprocess.run(['git', 'push', remote, branch], cwd=repo_path, check=True)
            
            print(f"Successfully pushed changes: {commit_message}")
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"Git command failed: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error: {e}")
            return False
    
    def on_closing(self):
        """Handle window close event"""
        if messagebox.askokcancel("Quit", "Do you want to quit the application?"):
            self.quit_app()
    
    def quit_app(self, icon=None, item=None):
        """Quit the application"""
        # Close any active dialog
        if self.active_dialog:
            try:
                self.active_dialog.destroy()
            except:
                pass
            self.active_dialog = None
            
        if self.observer:
            self.observer.stop()
            self.observer.join()
            
        if self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None
            
        self.root.quit()
        self.root.destroy()
        
    def run(self):
        """Run the application"""
        self.root.mainloop()


class CommitDialog:
    """Dialog for entering commit information - SIMPLIFIED VERSION"""
    
    def __init__(self, parent, app, file_path):
        self.app = app
        self.file_path = file_path
        
        # Create dialog - handle case where parent might be None
        if parent is None:
            # Create independent dialog window
            self.dialog = tk.Tk()
            self.dialog.withdraw()  # Hide briefly while setting up
        else:
            self.dialog = tk.Toplevel(parent)
        
        self.dialog.title("File Changed - Commit Changes")
        self.dialog.geometry("500x220")  # Larger to accommodate multi-line text
        
        # Make dialog always on top and properly visible
        self.dialog.attributes('-topmost', True)
        self.dialog.lift()
        self.dialog.focus_force()
        
        # Center the dialog on screen
        self.center_on_screen()
        
        # Make it modal, but handle grab errors gracefully
        if parent:
            self.dialog.transient(parent)
            
        try:
            self.dialog.grab_set()
        except tk.TclError as e:
            print(f"Warning: Could not set dialog grab: {e}")
        
        self.setup_simple_dialog()
        
        # Show the dialog if it was hidden
        if parent is None:
            self.dialog.deiconify()
            self.dialog.lift()
            self.dialog.focus_force()
            self.dialog.attributes('-topmost', True)  
            self.dialog.after(500, lambda: self.dialog.attributes('-topmost', False))
            self.dialog.after(100, lambda: self.set_initial_focus())
        else:
            self.dialog.after(50, lambda: self.set_initial_focus())
            
    def center_on_screen(self):
        """Center the dialog on the screen"""
        self.dialog.update_idletasks()
        width = 500  
        height = 220
        x = (self.dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (height // 2)
        self.dialog.geometry(f"{width}x{height}+{x}+{y}")

    def setup_simple_dialog(self):
        """Setup ONLY commit message - NO remote/branch fields"""
        # Clear any existing widgets first
        for widget in self.dialog.winfo_children():
            widget.destroy()
            
        main_frame = ttk.Frame(self.dialog, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # File info
        ttk.Label(main_frame, text=f"File changed: {os.path.basename(self.file_path)}", 
                 font=('Arial', 10, 'bold')).pack(pady=(0, 10))
        
        # ONLY commit message field
        commit_label_frame = ttk.Frame(main_frame)
        commit_label_frame.pack(fill=tk.X, pady=(0, 3))
        
        ttk.Label(commit_label_frame, text="📝 Commit Message:").pack(side=tk.LEFT)
        ttk.Label(commit_label_frame, text="(Ctrl+Enter to submit)", 
                 font=('Arial', 8), foreground='gray').pack(side=tk.RIGHT)
        
        # Create multi-line text widget with scrollbar
        text_frame = ttk.Frame(main_frame)
        text_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        self.commit_text = tk.Text(text_frame, height=5, width=60, 
                                  font=('Arial', 9), wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.commit_text.yview)
        self.commit_text.configure(yscrollcommand=scrollbar.set)
        
        self.commit_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Insert default text
        default_commit = f"Update {os.path.basename(self.file_path)} - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        self.commit_text.insert('1.0', default_commit)
        
        # Buttons - NO OTHER FIELDS
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="✅ Push Changes", 
                  command=self.push_changes).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="❌ Cancel", 
                  command=self.cancel).pack(side=tk.LEFT)
        
        # Bind keys (Ctrl+Enter to submit, Escape to cancel)
        self.dialog.bind('<Control-Return>', lambda e: self.push_changes())
        self.dialog.bind('<Escape>', lambda e: self.cancel())
        self.dialog.protocol("WM_DELETE_WINDOW", self.cancel)
        
        print(f"Multi-line dialog created with commit: '{default_commit[:30]}...'")
    
    def set_initial_focus(self):
        """Set focus on commit text widget"""
        try:
            self.commit_text.focus_set()
            self.commit_text.select_range('1.0', tk.END)
            print(f"Focus set on text widget")
        except Exception as e:
            print(f"Error setting focus: {e}")
    
    def push_changes(self):
        """Push changes using commit message from text widget"""
        commit_msg = self.commit_text.get('1.0', tk.END).strip()
        
        if not commit_msg:
            messagebox.showerror("Error", "Please enter a commit message")
            return
        
        # Get remote/branch from main app config (not from dialog)
        remote = self.app.config.get('default_remote', 'origin')
        branch = self.app.config.get('default_branch', 'main')
        
        print(f"Pushing commit: '{commit_msg[:50]}...' to {remote}/{branch}")
        
        # Disable dialog while processing
        self.commit_text.configure(state='disabled')
        
        # Run git commands in background
        def run_git():
            success = self.app.run_git_commands(
                self.app.config['repo_path'],
                commit_msg,
                remote,
                branch
            )
            self.app.root.after(0, lambda: self.show_result(success, commit_msg))
        
        threading.Thread(target=run_git, daemon=True).start()
    
    def show_result(self, success, commit_msg):
        """Show result message"""
        self.dialog.withdraw()
        
        # Show only the first line of commit message in success dialog
        first_line = commit_msg.split('\n')[0]
        display_msg = first_line if len(first_line) <= 50 else first_line[:50] + "..."
        
        if success:
            messagebox.showinfo("Success", f"✅ Changes pushed successfully!\n\nCommit: {display_msg}")
        else:
            messagebox.showerror("Error", "❌ Failed to push changes. Check console.")
        
        self.close_dialog()
    
    def cancel(self):
        """Cancel dialog"""
        self.close_dialog()
    
    def close_dialog(self):
        """Close dialog and cleanup"""
        if self.app.active_dialog == self.dialog:
            self.app.active_dialog = None
        self.dialog.destroy()


def main():
    """Main entry point"""
    try:
        app = GitAutoSyncApp()
        app.run()
    except KeyboardInterrupt:
        print("\nApplication interrupted by user")
    except Exception as e:
        print(f"Application error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()