#!/bin/bash

new="$1"
old="$2"

TSHARK_CSV_HEADER='"frame__time_epoch","eth__src","eth__dst","ip__src","ip__dst","tcp__srcport","tcp__dstport","udp__srcport","udp__dstport","tcp__flags__syn","tcp__flags__ack","tcp__flags__reset","tcp__seq","tcp__ack","dns__qry__name","dns__a","tls__handshake__extensions_server_name","frame__len","tcp__len","udp__length","_ws__col__Protocol"'

if [ -n "$old" ] && [ "$old" != "$new" ]; then
    filename="$(basename "$old")"
    target_base="${old%.tmp}"

    # Default output is .json; packet files are written as .csv.
    extension=".json"
    if [[ "$filename" == packets* ]]; then
        extension=".csv"

        # Prepend the tshark field header to each rotated packet CSV file.
        header_tmp="${old}.header"
        {
            printf '%s\n' "$TSHARK_CSV_HEADER"
            cat "$old"
        } > "$header_tmp"
        mv "$header_tmp" "$old"
    fi

    mv "$old" "${target_base}${extension}"
fi
