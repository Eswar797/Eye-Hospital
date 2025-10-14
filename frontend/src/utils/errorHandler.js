/**
 * Comprehensive error handling utility for API errors
 * Prevents React from trying to render error objects directly
 */

/**
 * Parse error from API response and return a human-readable string
 * @param {Error} error - The error object from axios or fetch
 * @returns {string} - Human-readable error message
 */
export const parseApiError = (error) => {
  console.error('API Error:', error);

  // Network error (no response from server)
  if (!error.response) {
    if (error.request) {
      return 'Unable to connect to server. Please check your connection.';
    }
    return error.message || 'An unexpected error occurred';
  }

  // Server responded with error
  const { data, status } = error.response;

  // Handle different error response formats
  if (!data) {
    return `Server error (${status})`;
  }

  // String error message
  if (typeof data === 'string') {
    return data;
  }

  // Object with detail property (most FastAPI errors)
  if (data.detail) {
    // String detail
    if (typeof data.detail === 'string') {
      return data.detail;
    }

    // Array of validation errors (FastAPI Pydantic validation)
    if (Array.isArray(data.detail)) {
      return data.detail
        .map((err) => {
          const location = err.loc ? err.loc.join('.') : 'unknown';
          const message = err.msg || 'Validation error';
          return `${location}: ${message}`;
        })
        .join(', ');
    }

    // Object detail (try to stringify)
    try {
      return JSON.stringify(data.detail);
    } catch (e) {
      return 'Invalid error format from server';
    }
  }

  // Object with message property
  if (data.message) {
    return data.message;
  }

  // Object with error property
  if (data.error) {
    return typeof data.error === 'string' ? data.error : JSON.stringify(data.error);
  }

  // Try to stringify the entire data object
  try {
    const stringified = JSON.stringify(data);
    // Don't return very long strings
    return stringified.length > 200 
      ? `Server error (${status}): ${stringified.substring(0, 200)}...` 
      : `Server error (${status}): ${stringified}`;
  } catch (e) {
    return `Server error (${status})`;
  }
};

/**
 * Wrapper for async API calls with automatic error handling
 * @param {Function} apiCall - Async function that makes the API call
 * @param {Function} onSuccess - Callback for successful response
 * @param {Function} onError - Callback for error (receives error message string)
 * @returns {Promise<boolean>} - Returns true if successful, false if error
 */
export const handleApiCall = async (apiCall, onSuccess, onError) => {
  try {
    const response = await apiCall();
    if (onSuccess) {
      onSuccess(response);
    }
    return true;
  } catch (error) {
    const errorMessage = parseApiError(error);
    if (onError) {
      onError(errorMessage);
    }
    return false;
  }
};

/**
 * Create a safe error setter for React state
 * This ensures only strings are set as error messages
 * @param {Function} setError - React setState function
 * @returns {Function} - Safe error setter
 */
export const createSafeErrorSetter = (setError) => {
  return (error) => {
    if (typeof error === 'string') {
      setError(error);
    } else if (error instanceof Error) {
      setError(parseApiError(error));
    } else if (error && typeof error === 'object') {
      // Axios error object
      if (error.response || error.request) {
        setError(parseApiError(error));
      } else {
        // Generic object
        try {
          setError(JSON.stringify(error));
        } catch (e) {
          setError('An error occurred');
        }
      }
    } else {
      setError('An unexpected error occurred');
    }
  };
};

/**
 * Validate API response data
 * @param {any} data - Response data to validate
 * @param {Object} schema - Expected schema (simple validation)
 * @returns {boolean} - True if valid
 * @throws {Error} - If validation fails
 */
export const validateResponseData = (data, schema) => {
  if (!data) {
    throw new Error('No data received from server');
  }

  for (const [key, type] of Object.entries(schema)) {
    if (!(key in data)) {
      throw new Error(`Missing required field: ${key}`);
    }
    
    const actualType = Array.isArray(data[key]) ? 'array' : typeof data[key];
    if (actualType !== type && data[key] !== null) {
      throw new Error(`Invalid type for ${key}: expected ${type}, got ${actualType}`);
    }
  }

  return true;
};

export default {
  parseApiError,
  handleApiCall,
  createSafeErrorSetter,
  validateResponseData,
};

