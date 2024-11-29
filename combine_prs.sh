#!/bin/bash

# get a list of outstanding prs
gh pr list --state open --limit 100 --json number,headRefName --template '{{range .}}{{printf "%.0f\t%s\n" .number .headRefName}}{{end}}' | tac - > pr_list.tsv

# get them 1 by 1
while read prnumber prname;do git fetch origin pull/${prnumber}/head:${prname};done < pr_list.tsv

# Repeat this manually for each branch
# git merge <branch1>
# fix conflicts
# git add <changed files>
# git commit -m 'conflicts resolved'
# git push

# submit a new pr
gh pr create --draft --assignee @me --fill --body 'feat: new combined pr for all RENEE dockers' --base dev 
