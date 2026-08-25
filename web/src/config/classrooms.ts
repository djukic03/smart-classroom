/**
 * Seat counts. The API has no capacity field on a classroom, so occupancy can
 * only be judged against a number kept here. Rooms not listed show the head
 * count as plain context instead of inventing a verdict.
 */
export const CAPACITY: Record<number, number> = {
  1: 30,
  2: 120,
  3: 24,
}
