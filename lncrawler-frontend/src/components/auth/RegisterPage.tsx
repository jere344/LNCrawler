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
  FormHelperText
} from '@mui/material';
import { Visibility, VisibilityOff } from '@mui/icons-material';
import { authService } from '../../services/api';

const RegisterPage: React.FC = () => {
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
  const [usernameDebounceTimer, setUsernameDebounceTimer] = useState<NodeJS.Timeout | null>(null);
  const [emailDebounceTimer, setEmailDebounceTimer] = useState<NodeJS.Timeout | null>(null);

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
        setErrors(prev => ({ ...prev, username: 'This username is already taken' }));
      }
    } catch (error) {
      console.error('Error checking username:', error);
    }
  };
  
  const checkEmail = async (email: string) => {
    try {
      const { email_exists } = await authService.checkUserExists({ email });
      if (email_exists) {
        setErrors(prev => ({ ...prev, email: 'This email is already registered' }));
      }
    } catch (error) {
      console.error('Error checking email:', error);
    }
  };

  const validateForm = () => {
    const newErrors: Record<string, string> = {};
    
    if (!formData.username.trim()) {
      newErrors.username = 'Username is required';
    } else if (formData.username.length < 3) {
      newErrors.username = 'Username must be at least 3 characters long';
    }
    
    if (!formData.email.trim()) {
      newErrors.email = 'Email is required';
    } else if (!/\S+@\S+\.\S+/.test(formData.email)) {
      newErrors.email = 'Email is invalid';
    }
    
    if (!formData.password) {
      newErrors.password = 'Password is required';
    } else if (formData.password.length < 8) {
      newErrors.password = 'Password must be at least 8 characters long';
    }
    
    if (formData.password !== formData.password2) {
      newErrors.password2 = 'Passwords do not match';
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
          setGeneralError('Registration failed. Please try again.');
        }
      } else {
        setGeneralError('Registration failed. Please try again.');
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
          Create Account
        </Typography>
        
        {generalError && <Alert severity="error" sx={{ mb: 2 }}>{generalError}</Alert>}
        
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
            label="Email Address"
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
            label="Password"
            type={showPassword ? 'text' : 'password'}
            id="password"
            autoComplete="new-password"
            value={formData.password}
            onChange={handleChange}
            error={!!errors.password}
            helperText={errors.password}
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
          
          <TextField
            margin="normal"
            required
            fullWidth
            name="password2"
            label="Confirm Password"
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
            Password must be at least 8 characters long
          </FormHelperText>
          
          <Button
            type="submit"
            fullWidth
            variant="contained"
            sx={{ mt: 3, mb: 2 }}
            disabled={loading || Object.keys(errors).length > 0}
          >
            {loading ? <CircularProgress size={24} /> : 'Create Account'}
          </Button>
          
          <Divider sx={{ my: 2 }} />
          
          <Box sx={{ textAlign: 'center' }}>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              Already have an account?
            </Typography>
            <Button
              component={Link}
              to="/login"
              variant="outlined"
              disabled={loading}
            >
              Sign In
            </Button>
          </Box>
        </Box>
      </Paper>
    </Container>
  );
};

export default RegisterPage;
