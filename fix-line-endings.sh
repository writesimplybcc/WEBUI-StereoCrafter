#!/bin/bash
# Fix Windows line endings (CRLF) to Unix line endings (LF)
# Run this if you get "$'\r': command not found" errors

echo "Fixing line endings for shell scripts..."

# Fix all .sh files
for file in *.sh; do
    if [ -f "$file" ]; then
        echo "  Fixing: $file"
        sed -i 's/\r$//' "$file" 2>/dev/null || dos2unix "$file" 2>/dev/null || perl -pi -e 's/\r\n/\n/g' "$file"
    fi
done

echo "Done! Line endings fixed."
echo ""
echo "You can now run your startup scripts:"
echo "  bash runpod-docker-startup.sh"
echo "  bash runpod-startup.sh"
