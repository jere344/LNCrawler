import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { 
  Box, 
  Button, 
  Container, 
  TextField, 
  Typography, 
  Paper, 
  Alert, 
  InputAdornment, 
  IconButton,
  Divider,
  CircularProgress,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions
} from '@mui/material';
import Visibility from '@mui/icons-material/Visibility';
import VisibilityOff from '@mui/icons-material/VisibilityOff';
import { useAuth } from '../../context/AuthContext';
import { authService } from '../../services/auth.service';
import type { ApiError } from '../../services/api';

const LoginPage: React.FC = () => {
  const { login } = useAuth();
  const { t } = useTranslation();

  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Forgot password state
  const [showForgotPassword, setShowForgotPassword] = useState(false);
  const [forgotEmail, setForgotEmail] = useState('');
  const [forgotLoading, setForgotLoading] = useState(false);
  const [forgotSuccess, setForgotSuccess] = useState(false);
  const [forgotError, setForgotError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      await login(username, password);
      navigate('/'); // Redirect to home page after successful login
    } catch (error) {
      const err = error as ApiError;
      if (err.response?.data?.error) {
        setError(err.response.data.error);
      } else if (err.response?.data?.detail) {
        setError(err.response.data.detail);
      } else {
        setError(t('auth.loginFailed'));
      }
      console.error('Login error:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleForgotPassword = async () => {
    setForgotLoading(true);
    setForgotError(null);

    try {
      await authService.forgotPassword(forgotEmail);
      setForgotSuccess(true);
    } catch (err) {
      const apiErr = err as ApiError;
      if (apiErr.response?.data?.email) {
        setForgotError(apiErr.response.data.email[0]);
      } else {
        setForgotError(t('auth.resetEmailFailed'));
      }
    } finally {
      setForgotLoading(false);
    }
  };

  const resetForgotPasswordForm = () => {
    setShowForgotPassword(false);
    setForgotEmail('');
    setForgotSuccess(false);
    setForgotError(null);
  };

  return (
    <Container maxWidth="sm">
      <Paper 
        elevation={3} 
        sx={{ 
          mt: 4, 
          p: 4, 
          display: 'flex', 
          flexDirection: 'column',
          borderRadius: 2
        }}
      >
        <Typography variant="h4" component="h1" gutterBottom align="center">
          {t('auth.signIn')}
        </Typography>
        
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        
        <Box component="form" onSubmit={handleSubmit} noValidate>
          <TextField
            margin="normal"
            required
            fullWidth
            id="username"
            label={t('auth.username')}
            name="username"
            autoComplete="username"
            autoFocus
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            disabled={loading}
          />
          <TextField
            margin="normal"
            required
            fullWidth
            name="password"
            label={t('auth.password')}
            type={showPassword ? 'text' : 'password'}
            id="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={loading}
            slotProps={{
              input: {
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton
                      aria-label={t('auth.togglePassword')}
                      onClick={() => setShowPassword(!showPassword)}
                      edge="end"
                    >
                      {showPassword ? <VisibilityOff /> : <Visibility />}
                    </IconButton>
                  </InputAdornment>
                ),
              }
            }}
          />
          
          <Button
            type="submit"
            fullWidth
            variant="contained"
            sx={{ mt: 3, mb: 2 }}
            disabled={loading}
          >
            {loading ? <CircularProgress size={24} /> : t('auth.signIn')}
          </Button>
          
          <Divider sx={{ my: 2 }} />
          
          <Box sx={{ textAlign: 'center' }}>
            <Typography variant="body2" gutterBottom sx={{
              color: "text.secondary"
            }}>
              {t('auth.noAccount')}
            </Typography>
            <Button
              component={Link}
              to="/register"
              variant="outlined"
              disabled={loading}
              sx={{ mb: 2 }}
            >
              {t('auth.createAccount')}
            </Button>
            
            <Typography
              variant="body2"
              sx={{
                color: "text.secondary",
                mt: 2
              }}>
              <Button
                variant="text"
                size="small"
                onClick={() => setShowForgotPassword(true)}
                disabled={loading}
              >
                {t('auth.forgotPassword')}
              </Button>
            </Typography>
          </Box>
        </Box>

        {/* Forgot Password Dialog */}
        <Dialog open={showForgotPassword} onClose={resetForgotPasswordForm} maxWidth="sm" fullWidth>
          <DialogTitle>{t('auth.resetPassword')}</DialogTitle>
          <DialogContent>
            {forgotSuccess ? (
              <Box sx={{ textAlign: 'center', py: 2 }}>
                <Typography variant="h6" gutterBottom sx={{
                  color: "success.main"
                }}>
                  {t('auth.emailSent')}
                </Typography>
                <Typography variant="body2" sx={{
                  color: "text.secondary"
                }}>
                  {t('auth.checkEmail')}
                </Typography>
              </Box>
            ) : (
              <>
                {forgotError && <Alert severity="error" sx={{ mb: 2 }}>{forgotError}</Alert>}
                <Typography
                  variant="body2"
                  sx={{
                    color: "text.secondary",
                    mb: 2
                  }}>
                  {t('auth.enterEmailReset')}
                </Typography>
                <TextField
                  label={t('auth.emailAddress')}
                  type="email"
                  fullWidth
                  margin="normal"
                  value={forgotEmail}
                  onChange={(e) => setForgotEmail(e.target.value)}
                  required
                />
              </>
            )}
          </DialogContent>
          <DialogActions>
            <Button onClick={resetForgotPasswordForm}>
              {forgotSuccess ? t('common.close') : t('common.cancel')}
            </Button>
            {!forgotSuccess && (
              <Button 
                onClick={handleForgotPassword}
                variant="contained"
                disabled={forgotLoading || !forgotEmail}
              >
                {forgotLoading ? <CircularProgress size={24} /> : t('auth.sendResetLink')}
              </Button>
            )}
          </DialogActions>
        </Dialog>
      </Paper>
    </Container>
  );
};

export default LoginPage;
