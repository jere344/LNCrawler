export const utils = {
  /**
   * Convert a string to a URL-friendly slug
   */
  slugify: (text: string): string => {
    return text
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/(^-|-$)/g, '')
      .replace(/--+/g, '-');
  }
};
