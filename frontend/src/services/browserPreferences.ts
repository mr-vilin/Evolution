export function readRenamedPreference(key: string, previousKey: string): string | null {
  const value = localStorage.getItem(key);
  if (value !== null) return value;

  const previous = localStorage.getItem(previousKey);
  if (previous === null) return null;

  try {
    localStorage.setItem(key, previous);
    localStorage.removeItem(previousKey);
  } catch {
    // 存储受限时仍可使用已读取的偏好。
  }
  return previous;
}
