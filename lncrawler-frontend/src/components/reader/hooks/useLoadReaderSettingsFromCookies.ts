import { useEffect, type Dispatch, type SetStateAction } from 'react';
import { getCookie } from '@utils/cookies';
import { READER_COOKIE_PREFIX } from '@utils/storage';
import { defaultSettings } from '../readerDefaults';
import { ReaderSettings as IReaderSettings } from '../ReaderSettings';
import { isValidTtsPref } from '../tts/ttsTypes';

export function useLoadReaderSettingsFromCookies(
  setReaderSettings: Dispatch<SetStateAction<IReaderSettings>>
) {
  // Load saved settings from cookies
  useEffect(() => {
    const loadSettingsFromCookies = () => {
      const newSettings = { ...defaultSettings };
      let hasChanges = false;

      Object.keys(defaultSettings).forEach(keyStr => {
        const key = keyStr as keyof IReaderSettings; // Use keyof for type safety
        const cookieValue = getCookie(READER_COOKIE_PREFIX + key);

        if (cookieValue !== undefined) {
          try {
            const parsedValue = JSON.parse(cookieValue);
            
            // Null defaults (fontFamily/fontColor/backgroundColor) accept any
            // value; otherwise require a type match with the default.
            // TTS values are also range/enum checked (bad values would
            // break playback, e.g. a speed of 0).
            if (isValidTtsPref(key, parsedValue) && (defaultSettings[key] === null || typeof parsedValue === typeof defaultSettings[key])) {
              // Safe due to the runtime type check above.
              (newSettings as Record<string, unknown>)[key] = parsedValue;
              hasChanges = true;
            } else {
              // Log a warning if types don't match, and use the default value
              console.warn(
                `Cookie for ${key} has incorrect type. Expected ${typeof defaultSettings[key]}, got ${typeof parsedValue}. Using default.`
              );
              // newSettings[key] already holds the default value from the initial spread
            }
          } catch (e) {
            // Log an error if parsing fails, and use the default value
            console.error(`Error parsing cookie value for ${key}. Using default.`, e);
            // newSettings[key] already holds the default value
          }
        }
      });

      if (hasChanges) {
        setReaderSettings(newSettings);
      }
    };

    loadSettingsFromCookies();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- setter from useState is stable
  }, []);
}
