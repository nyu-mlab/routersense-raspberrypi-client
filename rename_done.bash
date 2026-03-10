#!/bin/bash

new="$1"
old="$2"

if [ -n "$old" ] && [ "$old" != "$new" ]; then
    mv "$old" "${old%.tmp}.json"
fi
