/** "刚刚 / N 分钟前 / N 小时前 / N 天前", then a calendar date, for save timestamps. */
export function relativeTime(iso: string | undefined, now: Date = new Date()): string {
  if (!iso) return "";
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return "";
  const minutes = Math.floor((now.getTime() - then.getTime()) / 60000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} 天前`;
  const sameYear = then.getFullYear() === now.getFullYear();
  return sameYear ? `${then.getMonth() + 1} 月 ${then.getDate()} 日` : `${then.getFullYear()} 年 ${then.getMonth() + 1} 月 ${then.getDate()} 日`;
}
