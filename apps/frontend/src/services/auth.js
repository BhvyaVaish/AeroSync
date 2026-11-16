export const auth = {
  getToken: () => localStorage.getItem('aerosync_token'),
  getRefreshToken: () => localStorage.getItem('aerosync_refresh_token'),
  
  setTokens: (accessToken, refreshToken) => {
    localStorage.setItem('aerosync_token', accessToken);
    if (refreshToken) {
      localStorage.setItem('aerosync_refresh_token', refreshToken);
    }
  },
  
  clearTokens: () => {
    localStorage.removeItem('aerosync_token');
    localStorage.removeItem('aerosync_refresh_token');
  },
  
  isAuthenticated: () => !!localStorage.getItem('aerosync_token')
};
