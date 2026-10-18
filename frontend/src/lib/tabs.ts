// The ids that join a tab to its panel, for aria-controls and aria-labelledby.
export const tabId = (prefix: string, id: string) => `${prefix}-tab-${id}`
export const panelId = (prefix: string, id: string) => `${prefix}-panel-${id}`
