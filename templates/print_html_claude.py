import os
import sys
from pathlib import Path
import argparse

def print_html_files(directory='.', include_subdirs=False):
    """
    Print contents of all HTML files in the specified directory
    
    Args:
        directory (str): The directory to search for HTML files
        include_subdirs (bool): Whether to include subdirectories in the search
    """
    # Convert to absolute path
    directory = os.path.abspath(directory)
    
    # Verify directory exists
    if not os.path.isdir(directory):
        print(f"Error: Directory '{directory}' not found")
        return

    # Get list of HTML files
    if include_subdirs:
        html_files = list(Path(directory).rglob("*.html"))
    else:
        html_files = list(Path(directory).glob("*.html"))

    if not html_files:
        print(f"No HTML files found in {directory}")
        return

    # Print each file
    for file_path in html_files:
        try:
            # Print file separator
            print("\n" + "="*80)
            print(f"File: {file_path}")
            print("="*80 + "\n")
            
            # Read and print file contents
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
                print(content)
                
        except Exception as e:
            print(f"Error reading {file_path}: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description='Print contents of HTML files in a directory')
    parser.add_argument('directory', nargs='?', default='.', 
                      help='Directory to search for HTML files (default: current directory)')
    parser.add_argument('-r', '--recursive', action='store_true',
                      help='Include subdirectories in search')
    
    args = parser.parse_args()
    print_html_files(args.directory, args.recursive)

if __name__ == "__main__":
    main()