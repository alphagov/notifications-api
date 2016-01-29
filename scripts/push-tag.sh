#!/bin/bash

function pretty() {
  local blue="\033[34m"
  local reset="\033[0m"
  while read line; do
    echo -e "${blue}[publishing]${reset} ${line}"
  done
}

function warn() {
  local orange="\033[33m"
  local reset="\033[0m"
  while read line; do
    echo -e "${orange}[warning]${reset} ${line}"
  done
}

function get_sha(){
    REF=$(git log -n 1 -- VERSION --name-only)
    SHA=$(echo $REF | awk '{ print $2 }')

    echo "checking out ${SHA}" | pretty

    git checkout $SHA
}

function get_version(){
    VERSION=$(python setup.py --version)
    echo "latest version is ${VERSION}" | pretty
}

function push_tag_or_die(){
    TAG_EXISTS=$(git tag | grep -G "^${VERSION}$")
    if [ "$TAG_EXISTS" ]; then
        echo "Tag already exists, exiting" | warn
        exit 0
    else
        push_tag $VERSION
    fi
}

function push_tag(){
    git tag -a $VERSION -m "Version tag for ${VERSION}"
    echo "Pushing tags to github ${VERSION} to Github" | pretty
    git push origin --tags
}

function main(){
    get_sha
    get_version
    push_tag_or_die
}

main