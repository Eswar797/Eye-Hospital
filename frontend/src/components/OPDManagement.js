import React, { useState, useEffect } from 'react';
import {
  Box,
  AppBar,
  Toolbar,
  Typography,
  Button,
  Container,
  Grid,
  Card,
  CardContent,
  CardActions,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  Chip,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Alert,
  Paper,
  Typography as MuiTypography,
  Divider,
} from '@mui/material';
import {
  ArrowBack,
  Refresh,
  PlayArrow,
  Pause,
  LocalHospital,
  Visibility,
  PersonAdd,
  CheckCircle,
  Schedule,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useSocket } from '../contexts/SocketContext';
import axios from 'axios';

const OPDManagement = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { joinOPD, leaveOPD, onQueueUpdate, removeAllListeners } = useSocket();
  const [selectedOpd, setSelectedOpd] = useState('opd1');
  const [queue, setQueue] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [actionDialog, setActionDialog] = useState({ open: false, type: '', patient: null });

  const opdTypes = [
    { value: 'opd1', label: 'OPD 1' },
    { value: 'opd2', label: 'OPD 2' },
    { value: 'opd3', label: 'OPD 3' },
  ];

  useEffect(() => {
    fetchQueueData();
    fetchStats();
    
    // Join OPD room for real-time updates
    joinOPD(selectedOpd);
    
    // Set up socket listeners
    onQueueUpdate((data) => {
      if (data.opd_type === selectedOpd) {
        setQueue(data.queue);
      }
    });

    return () => {
      leaveOPD(selectedOpd);
      removeAllListeners();
    };
  }, [selectedOpd]);

  const fetchQueueData = async () => {
    try {
      const response = await axios.get(`http://localhost:8000/api/opd/${selectedOpd}/queue`);
      setQueue(response.data);
    } catch (error) {
      console.error('Failed to fetch queue:', error);
    }
  };

  const fetchStats = async () => {
    try {
      const response = await axios.get(`http://localhost:8000/api/opd/${selectedOpd}/stats`);
      setStats(response.data);
    } catch (error) {
      console.error('Failed to fetch stats:', error);
    }
  };

  const handleCallNext = async () => {
    setLoading(true);
    try {
      const response = await axios.post(`http://localhost:8000/api/opd/${selectedOpd}/call-next`);
      setSuccess(response.data.message);
      fetchQueueData();
      fetchStats();
    } catch (error) {
      setError(error.response?.data?.detail || 'Failed to call next patient');
    } finally {
      setLoading(false);
    }
  };

  const handleDilatePatient = (patient) => {
    setActionDialog({
      open: true,
      type: 'dilate',
      patient: patient,
    });
  };

  const handleReferPatient = (patient) => {
    setActionDialog({
      open: true,
      type: 'refer',
      patient: patient,
    });
  };

  const handleReturnDilated = (patient) => {
    setActionDialog({
      open: true,
      type: 'return_dilated',
      patient: patient,
    });
  };

  const confirmAction = async () => {
    const { type, patient } = actionDialog;
    setLoading(true);

    try {
      if (type === 'dilate') {
        await axios.post(`http://localhost:8000/api/opd/${selectedOpd}/dilate-patient/${patient.patient_id}`);
        setSuccess(`Patient ${patient.token_number} marked for dilation`);
      } else if (type === 'refer') {
        const targetOpd = actionDialog.targetOpd;
        await axios.post(`http://localhost:8000/api/patients/${patient.patient_id}/refer`, {
          to_opd: targetOpd,
        });
        setSuccess(`Patient ${patient.token_number} referred to ${targetOpd.toUpperCase()}`);
      } else if (type === 'return_dilated') {
        await axios.post(`http://localhost:8000/api/opd/${selectedOpd}/return-dilated/${patient.patient_id}`);
        setSuccess(`Patient ${patient.token_number} returned from dilation`);
      }
      
      setActionDialog({ open: false, type: '', patient: null });
      fetchQueueData();
      fetchStats();
    } catch (error) {
      setError(error.response?.data?.detail || 'Action failed');
    } finally {
      setLoading(false);
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
      pending: 'Waiting',
      in: 'In OPD',
      dilated: 'Dilated',
      referred: 'Referred',
      end_visit: 'Completed',
    };
    return statusLabels[status] || status;
  };

  const formatWaitingTime = (registrationTime) => {
    const now = new Date();
    const regTime = new Date(registrationTime);
    const diffMinutes = Math.floor((now - regTime) / (1000 * 60));
    return `${diffMinutes} min`;
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
            OPD Management - {selectedOpd.toUpperCase()}
          </Typography>
          <Button color="inherit" onClick={fetchQueueData} startIcon={<Refresh />}>
            Refresh
          </Button>
        </Toolbar>
      </AppBar>

      <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
        {/* OPD Selection */}
        <Grid container spacing={3} sx={{ mb: 3 }}>
          <Grid item xs={12}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Select OPD
                </Typography>
                <FormControl fullWidth>
                  <InputLabel>OPD</InputLabel>
                  <Select
                    value={selectedOpd}
                    onChange={(e) => setSelectedOpd(e.target.value)}
                    label="OPD"
                  >
                    {opdTypes.map((opd) => (
                      <MenuItem key={opd.value} value={opd.value}>
                        {opd.label}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </CardContent>
            </Card>
          </Grid>
        </Grid>

        {/* Statistics */}
        {stats && (
          <Grid container spacing={3} sx={{ mb: 3 }}>
            <Grid item xs={12} sm={6} md={3}>
              <Paper sx={{ p: 2, textAlign: 'center' }}>
                <MuiTypography variant="h4" color="primary">
                  {stats.total_patients}
                </MuiTypography>
                <MuiTypography variant="body2" color="text.secondary">
                  Total Patients
                </MuiTypography>
              </Paper>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Paper sx={{ p: 2, textAlign: 'center' }}>
                <MuiTypography variant="h4" color="warning.main">
                  {stats.pending_patients}
                </MuiTypography>
                <MuiTypography variant="body2" color="text.secondary">
                  Pending
                </MuiTypography>
              </Paper>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Paper sx={{ p: 2, textAlign: 'center' }}>
                <MuiTypography variant="h4" color="info.main">
                  {stats.in_opd_patients}
                </MuiTypography>
                <MuiTypography variant="body2" color="text.secondary">
                  In OPD
                </MuiTypography>
              </Paper>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Paper sx={{ p: 2, textAlign: 'center' }}>
                <MuiTypography variant="h4" color="success.main">
                  {stats.completed_today}
                </MuiTypography>
                <MuiTypography variant="body2" color="text.secondary">
                  Completed Today
                </MuiTypography>
              </Paper>
            </Grid>
          </Grid>
        )}

        {/* Alerts */}
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

        <Grid container spacing={3}>
          {/* Queue Management */}
          <Grid item xs={12} md={8}>
            <Card>
              <CardContent>
                <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                  <Typography variant="h6">
                    Patient Queue ({queue.length} patients)
                  </Typography>
                  <Button
                    variant="contained"
                    startIcon={<PlayArrow />}
                    onClick={handleCallNext}
                    disabled={loading || queue.length === 0}
                  >
                    Call Next Patient
                  </Button>
                </Box>
                
                <List>
                  {queue.map((patient, index) => (
                    <React.Fragment key={patient.id}>
                      <ListItem>
                        <ListItemText
                          primary={`${patient.position}. ${patient.token_number} - ${patient.patient_name}`}
                          secondary={`Age: ${patient.age} | Waiting: ${formatWaitingTime(patient.registration_time)}`}
                        />
                        <ListItemSecondaryAction>
                          <Box display="flex" alignItems="center" gap={1}>
                            <Chip
                              label={getStatusLabel(patient.status)}
                              color={getStatusColor(patient.status)}
                              size="small"
                            />
                            {patient.is_dilated && (
                              <Chip
                                label="Dilated"
                                color="secondary"
                                size="small"
                              />
                            )}
                            {patient.status === 'pending' && (
                              <IconButton
                                size="small"
                                onClick={() => handleDilatePatient(patient)}
                                color="secondary"
                              >
                                <Schedule />
                              </IconButton>
                            )}
                            {patient.status === 'dilated' && (
                              <IconButton
                                size="small"
                                onClick={() => handleReturnDilated(patient)}
                                color="primary"
                              >
                                <CheckCircle />
                              </IconButton>
                            )}
                            {patient.status === 'in' && (
                              <IconButton
                                size="small"
                                onClick={() => handleReferPatient(patient)}
                                color="error"
                              >
                                <PersonAdd />
                              </IconButton>
                            )}
                          </Box>
                        </ListItemSecondaryAction>
                      </ListItem>
                      {index < queue.length - 1 && <Divider />}
                    </React.Fragment>
                  ))}
                </List>
              </CardContent>
            </Card>
          </Grid>

          {/* Quick Actions */}
          <Grid item xs={12} md={4}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Quick Actions
                </Typography>
                <Box display="flex" flexDirection="column" gap={2}>
                  <Button
                    variant="outlined"
                    startIcon={<Visibility />}
                    onClick={() => navigate('/display')}
                    fullWidth
                  >
                    View Display Screen
                  </Button>
                  <Button
                    variant="outlined"
                    startIcon={<Refresh />}
                    onClick={fetchQueueData}
                    fullWidth
                  >
                    Refresh Queue
                  </Button>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        </Grid>

        {/* Action Dialog */}
        <Dialog open={actionDialog.open} onClose={() => setActionDialog({ open: false, type: '', patient: null })}>
          <DialogTitle>
            {actionDialog.type === 'dilate' && 'Dilate Patient'}
            {actionDialog.type === 'refer' && 'Refer Patient'}
            {actionDialog.type === 'return_dilated' && 'Return Dilated Patient'}
          </DialogTitle>
          <DialogContent>
            {actionDialog.patient && (
              <Typography variant="body1" gutterBottom>
                Patient: {actionDialog.patient.patient_name} ({actionDialog.patient.token_number})
              </Typography>
            )}
            
            {actionDialog.type === 'refer' && (
              <FormControl fullWidth sx={{ mt: 2 }}>
                <InputLabel>Refer to OPD</InputLabel>
                <Select
                  value={actionDialog.targetOpd || ''}
                  onChange={(e) => setActionDialog(prev => ({ ...prev, targetOpd: e.target.value }))}
                  label="Refer to OPD"
                >
                  {opdTypes.filter(opd => opd.value !== selectedOpd).map((opd) => (
                    <MenuItem key={opd.value} value={opd.value}>
                      {opd.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            )}
            
            {actionDialog.type === 'dilate' && (
              <Typography variant="body2" color="text.secondary">
                Patient will be given dilation drops and wait 30-40 minutes before returning.
              </Typography>
            )}
            
            {actionDialog.type === 'return_dilated' && (
              <Typography variant="body2" color="text.secondary">
                Patient is returning from dilation area.
              </Typography>
            )}
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setActionDialog({ open: false, type: '', patient: null })}>
              Cancel
            </Button>
            <Button
              onClick={confirmAction}
              variant="contained"
              disabled={loading || (actionDialog.type === 'refer' && !actionDialog.targetOpd)}
            >
              {loading ? 'Processing...' : 'Confirm'}
            </Button>
          </DialogActions>
        </Dialog>
      </Container>
    </Box>
  );
};

export default OPDManagement;

