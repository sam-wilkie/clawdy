export function GithubCorner({ hidden = false }: { hidden?: boolean }) {
  if (hidden) return null
  return (
    <a className="github-corner" href="https://github.com/sam-wilkie/clawdy" target="_blank" rel="noopener noreferrer">
      github.com/sam-wilkie
    </a>
  )
}
