```
# Create or clear the destination file in the current directory
> codecache.txt

# Find all python files starting from here (.), excluding ./venv, and process them
find . -path "./venv" -prune -o -name "*.py" -print | while read -r file; do
  # Append a header with the file path to the cache file
  echo "======== FILE: $file ========" >> codecache.txt
  
  # Append the actual content of the file
  cat "$file" >> codecache.txt
  
  # Add a couple of newlines for better spacing between files
  echo -e "\n\n" >> codecache.txt
done

echo "Code cache created successfully in backend/codecache.txt"
```


NOTE:
```
# /// to be changed in production
origins = ["*"] 

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```