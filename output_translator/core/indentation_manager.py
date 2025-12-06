"""
Indentation Manager for CAI to Python translation.
Manages indentation state throughout the translation process.
"""


class IndentationManager:
    """Manage indentation state throughout translation"""
    
    def __init__(self, base_indent: int = 0):
        self.base_indent = base_indent
        self.current_indent = base_indent
        self.indent_stack = [base_indent]
        self.control_structure_stack = []
    
    def enter_block(self, block_type: str):
        """Enter a new indented block"""
        self.current_indent += 1
        self.indent_stack.append(self.current_indent)
        self.control_structure_stack.append(block_type)
    
    def exit_block(self):
        """Exit current block"""
        if len(self.indent_stack) > 1:
            self.indent_stack.pop()
            self.current_indent = self.indent_stack[-1]
            if self.control_structure_stack:
                self.control_structure_stack.pop()
    
    def get_indent_string(self) -> str:
        """Get current indentation as string"""
        return '    ' * self.current_indent
    
    def align_with_if(self):
        """Align indentation for elif/else with their if"""
        # Find the most recent 'if' in the stack
        for i in range(len(self.control_structure_stack) - 1, -1, -1):
            if self.control_structure_stack[i] == 'if':
                # Set indent to the level of this if
                self.current_indent = self.indent_stack[i]
                # Trim stacks to this level
                self.indent_stack = self.indent_stack[:i+1]
                self.control_structure_stack = self.control_structure_stack[:i+1]
                break
    
    def reset(self):
        """Reset to initial state"""
        self.current_indent = self.base_indent
        self.indent_stack = [self.base_indent]
        self.control_structure_stack = []
    
    def get_current_level(self) -> int:
        """Get current indentation level"""
        return self.current_indent
    
    def set_level(self, level: int):
        """Set indentation level directly"""
        self.current_indent = max(0, level)
    
    def __repr__(self):
        return f"IndentationManager(level={self.current_indent}, stack={self.control_structure_stack})"
