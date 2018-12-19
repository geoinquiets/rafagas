#! /bin/bash
# pre-commit.sh
git stash -q --keep-index
ruby ./script/proof.rb
RESULT=$?
git stash pop -q
[ $RESULT -ne 0 ] && exit 1
exit 0