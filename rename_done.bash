#!/bin/bash

new="$1"
old="$2"

if [ -n "$old" ] && [ "$old" != "$new" ]; then
    filename="$(basename "$old")"
    target_base="${old%.tmp}"

    # Default output is .json; packet files are written as .csv.
    extension=".json"
    if [[ "$filename" == packets* ]]; then
        extension=".csv"
    fi

    mv "$old" "${target_base}${extension}"
fi
