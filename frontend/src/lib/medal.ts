const MEDALS = ['medal-1', 'medal-2', 'medal-3']

/** The medal class of a top 3 place: gold, silver, or bronze. Other places get no class. */
export function medal(position: number | null | undefined): string {
  return position && position >= 1 && position <= 3 ? MEDALS[position - 1] : ''
}
