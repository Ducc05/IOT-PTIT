export const pageSizeOptions = [10, 25, 50, 100] as const

export function validPageSize(value: number) {
  return pageSizeOptions.some(option => option === value)
}
