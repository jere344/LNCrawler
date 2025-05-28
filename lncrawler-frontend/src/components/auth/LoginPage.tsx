import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
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
import { Visibility, VisibilityOff } from '@mui/icons-material';
import { useAuth } from '../../context/AuthContext';
import { authService } from '../../services/auth.service';

const LoginPage: React.FC = () => {
  const { login } = useAuth();

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
    } catch (error: any) {
      if (error.response?.data?.error) {
        setError(error.response.data.error);
      } else if (error.response?.data?.detail) {
        setError(error.response.data.detail);
      } else {
        setError('Login failed. Please try again.');
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
    } catch (err: any) {
      if (err.response?.data?.email) {
        setForgotError(err.response.data.email[0]);
      } else {
        setForgotError('Failed to send reset email. Please try again.');
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
          Sign In
        </Typography>
        
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        
        <Box component="form" onSubmit={handleSubmit} noValidate>
          <TextField
            margin="normal"
            required
            fullWidth
            id="username"
            label="Username"
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
            label="Password"
            type={showPassword ? 'text' : 'password'}
            id="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={loading}
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton
                    aria-label="toggle password visibility"
                    onClick={() => setShowPassword(!showPassword)}
                    edge="end"
                  >
                    {showPassword ? <VisibilityOff /> : <Visibility />}
                  </IconButton>
                </InputAdornment>
              ),
            }}
          />
          
          <Button
            type="submit"
            fullWidth
            variant="contained"
            sx={{ mt: 3, mb: 2 }}
            disabled={loading}
          >
            {loading ? <CircularProgress size={24} /> : 'Sign In'}
          </Button>
          
          <Divider sx={{ my: 2 }} />
          
          <Box sx={{ textAlign: 'center' }}>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              Don't have an account?
            </Typography>
            <Button
              component={Link}
              to="/register"
              variant="outlined"
              disabled={loading}
              sx={{ mb: 2 }}
            >
              Create Account
            </Button>
            
            <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
              <Button
                variant="text"
                size="small"
                onClick={() => setShowForgotPassword(true)}
                disabled={loading}
              >
                Forgot Password?
              </Button>
            </Typography>
          </Box>
        </Box>

        {/* Forgot Password Dialog */}
        <Dialog open={showForgotPassword} onClose={resetForgotPasswordForm} maxWidth="sm" fullWidth>
          <DialogTitle>Reset Password</DialogTitle>
          <DialogContent>
            {forgotSuccess ? (
              <Box sx={{ textAlign: 'center', py: 2 }}>
                <Typography variant="h6" color="success.main" gutterBottom>
                  Email Sent!
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Check your email for password reset instructions.
                </Typography>
              </Box>
            ) : (
              <>
                {forgotError && <Alert severity="error" sx={{ mb: 2 }}>{forgotError}</Alert>}
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  Enter your email address and we'll send you a link to reset your password.
                </Typography>
                <TextField
                  label="Email Address"
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
              {forgotSuccess ? 'Close' : 'Cancel'}
            </Button>
            {!forgotSuccess && (
              <Button 
                onClick={handleForgotPassword}
                variant="contained"
                disabled={forgotLoading || !forgotEmail}
              >
                {forgotLoading ? <CircularProgress size={24} /> : 'Send Reset Link'}
              </Button>
            )}
          </DialogActions>
        </Dialog>
      </Paper>
    </Container>
  );
};

export default LoginPage;
