#!/bin/sh
# Lists every placeholder still to fill in. Upload only when this prints nothing.
grep -rno '<mark>\[[^]]*\]</mark>' --include=*.html . | sed 's/<mark>//; s/<\/mark>//'
grep -rn 'Wählen Sie den passenden Absatz\|Keep the matching paragraph' --include=*.html . | cut -c1-90
