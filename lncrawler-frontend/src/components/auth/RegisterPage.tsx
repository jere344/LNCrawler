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
  FormHelperText
} from '@mui/material';
import Visibility from '@mui/icons-material/Visibility';
import VisibilityOff from '@mui/icons-material/VisibilityOff';
import { authService } from '../../services/api';

const RegisterPage: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    password2: '',
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [showPassword, setShowPassword] = useState(false);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [usernameDebounceTimer, setUsernameDebounceTimer] = useState<ReturnType<typeof setTimeout> | null>(null);
  const [emailDebounceTimer, setEmailDebounceTimer] = useState<ReturnType<typeof setTimeout> | null>(null);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
    
    // Clear related error when user starts typing again
    if (errors[name]) {
      setErrors(prev => {
        const newErrors = { ...prev };
        delete newErrors[name];
        return newErrors;
      });
    }
    
    // Check username/email availability with debounce
    if (name === 'username' && value.length >= 3) {
      if (usernameDebounceTimer) clearTimeout(usernameDebounceTimer);
      const timer = setTimeout(() => checkUsername(value), 500);
      setUsernameDebounceTimer(timer);
    }
    
    if (name === 'email' && value.includes('@')) {
      if (emailDebounceTimer) clearTimeout(emailDebounceTimer);
      const timer = setTimeout(() => checkEmail(value), 500);
      setEmailDebounceTimer(timer);
    }
  };
  
  const checkUsername = async (username: string) => {
    try {
      const { username_exists } = await authService.checkUserExists({ username });
      if (username_exists) {
        setErrors(prev => ({ ...prev, username: t('auth.usernameTaken') }));
      }
    } catch (error) {
      console.error('Error checking username:', error);
    }
  };
  
  const checkEmail = async (email: string) => {
    try {
      const { email_exists } = await authService.checkUserExists({ email });
      if (email_exists) {
        setErrors(prev => ({ ...prev, email: t('auth.emailRegistered') }));
      }
    } catch (error) {
      console.error('Error checking email:', error);
    }
  };

  const validateForm = () => {
    const newErrors: Record<string, string> = {};
    
    if (!formData.username.trim()) {
      newErrors.username = t('auth.usernameRequired');
    } else if (formData.username.length < 3) {
      newErrors.username = t('auth.usernameTooShort');
    }
    
    if (!formData.email.trim()) {
      newErrors.email = t('auth.emailRequired');
    } else if (!/\S+@\S+\.\S+/.test(formData.email)) {
      newErrors.email = t('auth.emailInvalid');
    }
    
    if (!formData.password) {
      newErrors.password = t('auth.passwordRequired');
    } else if (formData.password.length < 8) {
      newErrors.password = t('auth.passwordTooShort');
    }
    
    if (formData.password !== formData.password2) {
      newErrors.password2 = t('auth.passwordsNoMatch');
    }
    
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setGeneralError(null);
    
    if (!validateForm()) return;
    
    setLoading(true);
    try {
      await authService.register(formData);
      // Login automatically after successful registration
      await authService._login({
        username: formData.username,
        password: formData.password
      });
      navigate('/'); // Redirect to home after successful registration and login
    } catch (error: any) {
      if (error.response?.data) {
        // Handle validation errors from the server
        const serverErrors = error.response.data;
        const newErrors: Record<string, string> = {};
        
        Object.entries(serverErrors).forEach(([key, value]) => {
          if (Array.isArray(value) && value.length > 0) {
            newErrors[key] = value[0] as string;
          } else if (typeof value === 'string') {
            newErrors[key] = value;
          }
        });
        
        if (Object.keys(newErrors).length > 0) {
          setErrors(newErrors);
        } else {
          setGeneralError(t('auth.registrationFailed'));
        }
      } else {
        setGeneralError(t('auth.registrationFailed'));
      }
      console.error('Registration error:', error);
    } finally {
      setLoading(false);
    }
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
          {t('auth.createAccount')}
        </Typography>
        
        {generalError && <Alert severity="error" sx={{ mb: 2 }}>{generalError}</Alert>}
        
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
            value={formData.username}
            onChange={handleChange}
            error={!!errors.username}
            helperText={errors.username}
            disabled={loading}
          />
          
          <TextField
            margin="normal"
            required
            fullWidth
            id="email"
            label={t('auth.emailAddress')}
            name="email"
            autoComplete="email"
            value={formData.email}
            onChange={handleChange}
            error={!!errors.email}
            helperText={errors.email}
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
            autoComplete="new-password"
            value={formData.password}
            onChange={handleChange}
            error={!!errors.password}
            helperText={errors.password}
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
          
          <TextField
            margin="normal"
            required
            fullWidth
            name="password2"
            label={t('auth.confirmPassword')}
            type={showPassword ? 'text' : 'password'}
            id="password2"
            autoComplete="new-password"
            value={formData.password2}
            onChange={handleChange}
            error={!!errors.password2}
            helperText={errors.password2}
            disabled={loading}
          />
          
          <FormHelperText>
            {t('auth.passwordTooShort')}
          </FormHelperText>
          
          <Button
            type="submit"
            fullWidth
            variant="contained"
            sx={{ mt: 3, mb: 2 }}
            disabled={loading || Object.keys(errors).length > 0}
          >
            {loading ? <CircularProgress size={24} /> : t('auth.createAccount')}
          </Button>
          
          <Divider sx={{ my: 2 }} />
          
          <Box sx={{ textAlign: 'center' }}>
            <Typography variant="body2" gutterBottom sx={{
              color: "text.secondary"
            }}>
              {t('auth.alreadyHaveAccount')}
            </Typography>
            <Button
              component={Link}
              to="/login"
              variant="outlined"
              disabled={loading}
            >
              {t('auth.signIn')}
            </Button>
          </Box>
        </Box>
      </Paper>
    </Container>
  );
};

export default RegisterPage;
