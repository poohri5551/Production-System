export const FORECAST_COLUMN_LABELS = Object.freeze({
  quantity: "Q'ty",
  lotCount: 'Lot',
  quantityPerLot: "Q'ty/Lot",
})

export function chooseDefaultForecastMonth(months, now = new Date()) {
  const keys = [...new Set((months || []).map((item) => item.month))].sort()
  if (!keys.length) return null
  const current = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  if (keys.includes(current)) return current
  const notAfter = keys.filter((key) => key <= current)
  return notAfter.length ? notAfter[notAfter.length - 1] : keys[0]
}
