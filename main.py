import sys
import argparse
import os
from toolkit import AstroPreprocessor

def main():
    parser = argparse.ArgumentParser(description="RAW/FITS Preprocessing Toolkit")
    parser.add_argument("--cli", action="store_true", help="Run in CLI mode")
    parser.add_argument("--input", type=str, help="Input directory for CLI mode")
    parser.add_argument("--output", type=str, default="processed_fits", help="Output directory")
    
    args, unknown = parser.parse_known_args()

    if args.cli or args.input:
        # CLI Mode
        processor = AstroPreprocessor(output_dir=args.output)
        raw_directory = args.input or "./my_raw_files"
        
        if os.path.exists(raw_directory):
            files = [os.path.join(raw_directory, f) for f in os.listdir(raw_directory) 
                     if f.lower().endswith(('.cr2', '.nef', '.arw', '.dng'))]
            print(f"Core Tasks: Processing {len(files)} files...")
            processor.batch_convert(files, args.output)
        else:
            print(f"Directory {raw_directory} not found.")
    else:
        # GUI Mode
        try:
            from app import QApplication, MainWindow
            app = QApplication(sys.argv)
            window = MainWindow()
            window.show()
            sys.exit(app.exec())
        except ImportError:
            print("PyQt6 not found. Please run 'pip install PyQt6 matplotlib' or use --cli")

if __name__ == "__main__":
    main()