export const setCookie = (
  name: string,
  value: string,
  days = 365,
  sameSite: 'Strict' | 'Lax' | 'None' = 'Strict',
): void => {
  const expires = new Date(Date.now() + days * 864e5).toUTCString();
  document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/; SameSite=${sameSite}`;
};

export const getCookie = (name: string): string | undefined => {
  const match = document.cookie.split('; ').find((row) => row.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : undefined;
};
