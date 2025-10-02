import React, { useState, useEffect } from 'react';
import {
  Box,
  AppBar,
  Toolbar,
  Typography,
  Button,
  Container,
  Card,
  CardContent,
  TextField,
  Grid,
  Alert,
  Paper,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  IconButton,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
} from '@mui/material';
import {
  ArrowBack,
  PersonAdd,
  Print,
  Refresh,
  CheckCircle,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import axios from 'axios';

const PatientRegistration = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [formData, setFormData] = useState({
    name: '',
    age: '',
    phone: '',
  });
  const [patients, setPatients] = useState([]);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState('');
  const [error, setError] = useState('');
  const [selectedPatient, setSelectedPatient] = useState(null);
  const [opdDialogOpen, setOpdDialogOpen] = useState(false);
  const [selectedOpd, setSelectedOpd] = useState('');

  const opdTypes = [
    { value: 'opd1', label: 'OPD 1' },
    { value: 'opd2', label: 'OPD 2' },
    { value: 'opd3', label: 'OPD 3' },
  ];

  useEffect(() => {
    fetchPatients();
  }, []);

  const fetchPatients = async () => {
    try {
      const response = await axios.get('http://localhost:8000/api/patients');
      setPatients(response.data);
    } catch (error) {
      console.error('Failed to fetch patients:', error);
    }
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setSuccess('');

    try {
      const response = await axios.post('http://localhost:8000/api/patients/register', {
        name: formData.name,
        age: parseInt(formData.age),
        phone: formData.phone || null,
      });

      setSuccess(`Patient registered successfully! Token: ${response.data.token_number}`);
      setFormData({ name: '', age: '', phone: '' });
      fetchPatients();
    } catch (error) {
      setError(error.response?.data?.detail || 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  const handleAllocateOpd = (patient) => {
    setSelectedPatient(patient);
    setOpdDialogOpen(true);
  };

  const confirmOpdAllocation = async () => {
    if (!selectedPatient || !selectedOpd) return;

    try {
      const response = await axios.post(`http://localhost:8000/api/patients/${selectedPatient.id}/allocate-opd`, {
        opd_type: selectedOpd,
      });

      setSuccess(`Patient allocated to ${selectedOpd.toUpperCase()}. Queue position: ${response.data.queue_position}`);
      setOpdDialogOpen(false);
      setSelectedPatient(null);
      setSelectedOpd('');
      fetchPatients();
    } catch (error) {
      setError(error.response?.data?.detail || 'OPD allocation failed');
    }
  };

  const getStatusColor = (status) => {
    const statusColors = {
      pending: 'warning',
      in: 'info',
      dilated: 'secondary',
      referred: 'error',
      end_visit: 'success',
    };
    return statusColors[status] || 'default';
  };

  const getStatusLabel = (status) => {
    const statusLabels = {
      pending: 'Pending',
      in: 'In OPD',
      dilated: 'Dilated',
      referred: 'Referred',
      end_visit: 'Completed',
    };
    return statusLabels[status] || status;
  };

  return (
    <Box sx={{ flexGrow: 1 }}>
      <AppBar position="static">
        <Toolbar>
          <IconButton
            edge="start"
            color="inherit"
            onClick={() => navigate('/dashboard')}
            sx={{ mr: 2 }}
          >
            <ArrowBack />
          </IconButton>
          <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
            Patient Registration
          </Typography>
          <Button color="inherit" onClick={fetchPatients} startIcon={<Refresh />}>
            Refresh
          </Button>
        </Toolbar>
      </AppBar>

      <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
        <Grid container spacing={3}>
          {/* Registration Form */}
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Register New Patient
                </Typography>
                
                {error && (
                  <Alert severity="error" sx={{ mb: 2 }}>
                    {error}
                  </Alert>
                )}
                
                {success && (
                  <Alert severity="success" sx={{ mb: 2 }}>
                    {success}
                  </Alert>
                )}

                <Box component="form" onSubmit={handleSubmit}>
                  <TextField
                    margin="normal"
                    required
                    fullWidth
                    id="name"
                    label="Patient Name"
                    name="name"
                    value={formData.name}
                    onChange={handleInputChange}
                  />
                  <TextField
                    margin="normal"
                    required
                    fullWidth
                    id="age"
                    label="Age"
                    name="age"
                    type="number"
                    value={formData.age}
                    onChange={handleInputChange}
                  />
                  <TextField
                    margin="normal"
                    fullWidth
                    id="phone"
                    label="Phone Number"
                    name="phone"
                    value={formData.phone}
                    onChange={handleInputChange}
                  />
                  <Button
                    type="submit"
                    fullWidth
                    variant="contained"
                    sx={{ mt: 3, mb: 2 }}
                    disabled={loading}
                    startIcon={<PersonAdd />}
                  >
                    {loading ? 'Registering...' : 'Register Patient'}
                  </Button>
                </Box>
              </CardContent>
            </Card>
          </Grid>

          {/* Patient List */}
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Recent Patients
                </Typography>
                <List>
                  {patients.slice(0, 10).map((patient) => (
                    <ListItem key={patient.id} divider>
                      <ListItemText
                        primary={`${patient.token_number} - ${patient.name}`}
                        secondary={`Age: ${patient.age} | Status: ${getStatusLabel(patient.current_status)}`}
                      />
                      <ListItemSecondaryAction>
                        <Chip
                          label={getStatusLabel(patient.current_status)}
                          color={getStatusColor(patient.current_status)}
                          size="small"
                        />
                        {!patient.allocated_opd && (
                          <IconButton
                            edge="end"
                            onClick={() => handleAllocateOpd(patient)}
                            color="primary"
                          >
                            <PersonAdd />
                          </IconButton>
                        )}
                      </ListItemSecondaryAction>
                    </ListItem>
                  ))}
                </List>
              </CardContent>
            </Card>
          </Grid>

          {/* All Patients Table */}
          <Grid item xs={12}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  All Patients
                </Typography>
                <List>
                  {patients.map((patient) => (
                    <ListItem key={patient.id} divider>
                      <ListItemText
                        primary={`${patient.token_number} - ${patient.name}`}
                        secondary={`Age: ${patient.age} | Phone: ${patient.phone || 'N/A'} | Registered: ${new Date(patient.registration_time).toLocaleString()}`}
                      />
                      <ListItemSecondaryAction>
                        <Box display="flex" alignItems="center" gap={1}>
                          <Chip
                            label={getStatusLabel(patient.current_status)}
                            color={getStatusColor(patient.current_status)}
                            size="small"
                          />
                          {patient.allocated_opd && (
                            <Chip
                              label={patient.allocated_opd.toUpperCase()}
                              color="primary"
                              size="small"
                            />
                          )}
                          {!patient.allocated_opd && (
                            <IconButton
                              edge="end"
                              onClick={() => handleAllocateOpd(patient)}
                              color="primary"
                            >
                              <PersonAdd />
                            </IconButton>
                          )}
                        </Box>
                      </ListItemSecondaryAction>
                    </ListItem>
                  ))}
                </List>
              </CardContent>
            </Card>
          </Grid>
        </Grid>

        {/* OPD Allocation Dialog */}
        <Dialog open={opdDialogOpen} onClose={() => setOpdDialogOpen(false)}>
          <DialogTitle>Allocate OPD</DialogTitle>
          <DialogContent>
            <Typography variant="body1" gutterBottom>
              Patient: {selectedPatient?.name} ({selectedPatient?.token_number})
            </Typography>
            <FormControl fullWidth sx={{ mt: 2 }}>
              <InputLabel>Select OPD</InputLabel>
              <Select
                value={selectedOpd}
                onChange={(e) => setSelectedOpd(e.target.value)}
                label="Select OPD"
              >
                {opdTypes.map((opd) => (
                  <MenuItem key={opd.value} value={opd.value}>
                    {opd.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setOpdDialogOpen(false)}>Cancel</Button>
            <Button onClick={confirmOpdAllocation} variant="contained">
              Allocate
            </Button>
          </DialogActions>
        </Dialog>
      </Container>
    </Box>
  );
};

export default PatientRegistration;

